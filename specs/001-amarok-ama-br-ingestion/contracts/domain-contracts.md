# Contrato: Domínio parseado (parser → raw domain model)

**Feature**: `001-amarok-ama-br-ingestion` — ver [../data-model.md](../data-model.md) para os tipos de entidade completos, e [../research.md](../research.md) §16 para a decisão de separar os três níveis abaixo (correção da revisão de TASKS — anteriormente tudo estava concentrado em um único `parse_spec_entry()`, o que não refletia a evidência real de navegação da fonte nem implementava FR-001).

Três parsers, cada um recebendo HTML/raw **já adquirido** (nenhum faz networking), roteados por `RawCaptureInput.capture_kind` (contracts/input-contracts.md):

```
Nível A (MARKET_INDEX)      Nível B (SPEC_NAVIGATION)      Nível C (GROUP_DETAIL)
parse_market_spec_index()   parse_spec_group_manifest()    parse_group_detail()
→ list[DiscoveredSpecEntry] → SpecGroupManifest             → ParsedGroupDetail
```

---

## Nível A — Market Index

**Objetivo**: implementar FR-001 ("descobrir/enumerar os spec entries do Volkswagen Amarok no mercado AMA BR"), antes não implementado.

```
parse_market_spec_index(html, source_capture_id) -> ParseMarketIndexResult

ParseMarketIndexResult:
  entries: list[DiscoveredSpecEntry]             # ver data-model.md §14
  parse_errors: list[ParseError]                 # não-críticos, por entrada
  critical_error: ParseError | null              # presente ⇒ INVALID, nenhuma entrada é confiável
```

Cada `DiscoveredSpecEntry` preserva, quando presentes na fonte: `market`, `model_code`, `amayama_catalog_id`, `production_period_raw` (com melhor esforço de parsing para `production_start`/`production_end`, incluindo períodos open-ended), `source_url` (link para a página de navegação — Nível B), e `grade`/`configuração` **somente quando comprovados**. `model_code` isolado nunca é usado como identificador (mesma regra de FR-003).

**Seletores/estratégia de extração — comprovados (2026-08-26, browser-in-the-loop, DEC-001)**: gap fechado por evidência real fornecida pelo PO (research.md §21). Container `.epcVariations`; cada spec entry é uma `.epcVariations__row` com exatamente 3 `<td>`. `model_code` vem do texto do `<a>` na 1ª `<td>` (nunca reconstruído do slug da URL); `source_url` é o `href` absoluto desse mesmo `<a>`; `amayama_catalog_id` é o sufixo numérico final do último segmento de path dessa URL (`-(\d+)$`), nunca uma decodificação do `model_code`. `production_period_raw` é o texto da 2ª `<td>` (formato `YYYY.MM - YYYY.MM`, com `"..."` como término open-ended → `production_end=None`). `grade` é o texto de `span.info-hint-new` na 3ª `<td>`, quando presente. `market` é validado pela identidade estrutural da própria página (`.breadcrumbs__last-item`, ex. texto `"AMA BR"` → `"AMA-BR"`), nunca inferido de `grade`/`model_code`. `configuration` não tem fonte estrutural comprovada nesta captura — permanece sempre `None` (nunca derivado de `grade`).

**Fixtures reais** (`tests/fixtures/market_index/`, minimizadas da captura manual de 2026-08-26): `valid_multi_entry` (múltiplos spec entries); `same_model_code_diff_catalog` (regressão real S7BC8A: catalog `62184` vs `61189`, provando que `model_code` isolado nunca identifica uma spec entry); `open_ended_period`; `missing_optional_field` (mutação real-derivada: grade ausente); `structural_drift` (mutação real-derivada: container renomeado).

---

## Nível B — Spec Group Manifest

**Objetivo**: enumerar `Category` → `Group` esperados para uma spec entry, fechando o gap de "quais são todos os grupos esperados" (research.md §17, data-model.md §15).

```
parse_spec_group_manifest(html, spec_key, source_capture_id) -> ParseManifestResult

ParseManifestResult:
  manifest: SpecGroupManifest | null              # ver data-model.md §15; null se critical_error
  parse_errors: list[ParseError]
  critical_error: ParseError | null               # presente ⇒ manifesto NÃO é autoritativo (data-model.md §15)
```

**Invariante — `group_id` duplicado (movida do Nível C para o Nível B)**: se dois `(category_slug, group_id)` no manifesto colidem, isso é `critical_error` — o manifesto inteiro não é autoritativo (data-model.md §15, regra 4). Esta é a mesma invariante estrutural de `data-model.md` §2, agora verificada no nível em que a enumeração de grupos realmente acontece (a árvore de detalhe, Nível C, não enumera grupos — ela é indexada por um `(category_slug, group_id)` já conhecido pelo manifesto).

**`manifest_complete`**: `True` somente se a página de navegação foi processada até o fim sem truncamento nem `critical_error`. Uma extração parcial (ex.: paginação não totalmente percorrida) produz `manifest_complete = False`, e o manifesto correspondente não é autoritativo.

**Seletores/estratégia de extração — comprovados (2026-08-26, browser-in-the-loop, DEC-001)**: gap fechado por evidência real fornecida pelo PO (research.md §21). Raiz `.epcVariation__details` (compartilhada com Nível C — mesma família de template do site; o roteamento por `capture_kind` evita ambiguidade). Navegação de categorias em `.epcVariation__schemaGroups > a.epcVariation__schemaGroup`; o link com `data-id=""` (texto "All") **nunca** representa uma categoria de domínio e é sempre ignorado; `category_slug` de cada categoria real vem do último segmento do `href`. O universo de Groups é `.epcVariation__schemas .epcVariation__schema[data-id]`; para cada card, `group_id = data-id` e a URL canônica vem de `.epcVariation__schema-name a[href]`, cujos dois últimos segmentos são `(category_slug, group_id)` — **essa é a mesma URL usada por `extract_category_and_group_from_url()`** (ver Nível C abaixo), garantindo consistência entre os dois níveis. Invariante `card data-id == último segmento do href` verificada explicitamente; divergência é `critical_error` (nunca se escolhe arbitrariamente um dos dois lados). `category_slug` do card ausente da navegação declarada também é `critical_error` estrutural.

**`manifest_complete` — limitação de observabilidade registrada (research.md §21)**: a evidência estática disponível não permite distinguir "manifesto legitimamente menor" de "manifesto truncado mas estruturalmente perfeito" (ex.: lazy-load de infinite scroll interrompido) — nenhuma cardinalidade/contagem é usada como heurística de truncamento. O único sinal estruturalmente observável e usado em v1 é o caso degenerado "`.epcVariation__schemas` presente porém vazio, apesar de a navegação declarar categorias" → `manifest_complete=False`. Uma truncagem parcial (parte dos cards ausente) não é detectável nesta versão e permanece um gap registrado, não uma heurística inventada.

**Fixtures reais** (`tests/fixtures/spec_navigation/`, minimizadas da captura manual de 2026-08-26, spec `S1BC3X-56087`): `valid_manifest` (múltiplas categorias/grupos reais); `duplicate_group_id` (mutação real-derivada: `critical_error`, manifesto não-autoritativo); `truncated_manifest` (mutação real-derivada: container de groups vazio → `manifest_complete=False`); `structural_drift` (mutação real-derivada: `data-id` do card divergente do último segmento da URL → `critical_error`).

---

## Nível C — Group Detail

**Seletores v1** (contrato de parser, não implementação). Evidência técnica já pesquisada. O parser v1 DEVE usar exatamente estes seletores como contrato inicial; qualquer divergência estrutural encontrada em runtime DEVE produzir um erro explícito de drift (nunca parsing permissivo que oculte a divergência — ponto 20 do PLAN):

| Papel | Seletor CSS |
|---|---|
| Detalhes da variação | `.epcVariation__details` |
| Container de schemas | `.epcSchema__schemas` |
| Schema individual | `.epcSchema__schema[data-id]` |
| Descrição de imagem | `.img__description` |
| Imagem | `.imgMap img[src]` |
| Tabela de peças | `.entriesTable` |
| Wrapper de linha PNC | `tr[data-key]` |
| Cabeçalho de grupo | `.entriesPncTable__groupHeader` |
| OEM (código da peça) | `.entriesTable__number` |
| Descrição (peça) | `.entriesTable__description` |
| Descrição aninhada | `.entriesPncDescriptionTable` |
| Período/aplicação | `.entriesTable__period` |
| Quantidade | `.entriesTable__required` |

### Extração de `category_slug`/`group_id` (research.md §19 — resolvida com evidência de URL)

```
extract_category_and_group_from_url(source_url: str) -> (category_slug: str, group_id: str)
  # contrato v1: os dois segmentos finais do path da URL, nessa ordem
  # ex.: ".../s1bc3x-56087/front-axle-steering/407" → ("front-axle-steering", "407")
  # FALHA EXPLÍCITA (drift estrutural) se a URL não tiver esse formato — nunca infere
  # a partir de texto visível/traduzido da página
```

**Gap remanescente registrado sem invenção**: ainda não há evidência confirmando que todas as páginas de grupo seguem esse padrão de exatamente 2 segmentos finais, sem aninhamento adicional — o contrato v1 assume esse padrão e falha explicitamente quando não corresponde (ver research.md §19).

### Resultado de parsing

```
ParsedGroupDetail:
  category_slug: str                             # extraído da URL (ver acima) ou recebido como parâmetro
  group_id: str                                   # idem — string, preserva zeros à esquerda, nunca int
  schemas: list[ParsedSchema]                     # pode ser vazio — grupo vazio é válido e preservado
  parse_errors: list[ParseError]                  # não-críticos
  critical_error: ParseError | null               # presente ⇒ INVALID, este Group não pode ser ACCEPTED

ParsedSchema:
  schema_id: str
  parts: list[ParsedPart]

ParsedPart:
  field_status: dict[str, "PRESENT" | "ABSENT" | "PARSE_ERROR"]   # por campo, ver abaixo
  # campos de dado conforme data-model.md §3 (Part)
```

### Distinção obrigatória: campo ausente vs. erro de parsing

Para cada campo opcional de `Part` (`oem_code`, `description`, `details`, `period_application_text`, `pr_codes`, `quantity`, `image_url`), o resultado de parsing DEVE marcar `field_status` como (nota: `pr_codes` é parseado e preservado normalmente aqui, mesmo não participando do `part_fingerprint` v1 — ver `contracts/normalization-fingerprint-contracts.md`):

- `PRESENT`: o campo foi extraído com sucesso.
- `ABSENT`: o seletor correspondente não encontrou o elemento esperado — tratado como ausência legítima (FR-014), NÃO é erro.
- `PARSE_ERROR`: o elemento existe mas seu conteúdo não pôde ser extraído de forma confiável (ex.: estrutura interna inesperada) — registrado em `parse_errors`, não invalida a peça inteira por si só, mas é evidência para auditoria/observabilidade.

---

## Montagem da árvore agregada (`assemble_spec_tree`)

Os fingerprints hierárquicos (`contracts/normalization-fingerprint-contracts.md`) precisam de uma árvore completa `Category → Group → Schema → Part`. Como essa árvore agora é produzida incrementalmente (um `ParsedGroupDetail` por captura, tipicamente), uma função de montagem combina o manifesto (Nível B, define o universo esperado) com os `ParsedGroupDetail` já `ACCEPTED` (Nível C):

```
assemble_spec_tree(manifest: SpecGroupManifest, group_details: dict[(category_slug, group_id), ParsedGroupDetail]) -> AssembledSpecTree

AssembledSpecTree:
  categories: list[Category]   # data-model.md §2 — cada Category com seus Group já preenchidos
                                # com os ParsedGroupDetail disponíveis em group_details
```

**Regra**: `assemble_spec_tree()` só produz uma árvore utilizável para fingerprint/snapshot `VALID` quando o manifesto é autoritativo (data-model.md §15) **e** todo `(category_slug, group_id)` do manifesto tem uma entrada correspondente em `group_details` (equivalente a `collection_complete == True`, ver data-model.md §6). Grupos do manifesto ainda sem `ParsedGroupDetail` produzem uma árvore parcial, usada apenas para snapshot `INCOMPLETE` (nunca `VALID`).

**Rastreabilidade**: FR-001, FR-002, FR-012, FR-013, FR-014, FR-026, edge case "campo opcional ausente", edge case "duplicate group_id".
