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

**Seletores/estratégia de extração**: não pesquisados/evidenciados até o momento — este é um gap de pesquisa explícito, análogo ao de `category_slug` antes desta revisão. **Registrado sem invenção**: a estrutura concreta da página de índice do mercado AMA-BR (lista de spec entries, formato de URL de cada uma) precisa ser verificada contra uma fixture real antes da implementação — mesma disciplina de "investigação técnica localizada, não autorização para browser automation" aplicada a `category_slug` (ver Nível B/C abaixo e research.md §19).

**Fixtures previstas** (tasks.md): múltiplos spec entries em uma única página de índice; mesmo `model_code` com `amayama_catalog_id` distintos; período open-ended; campo opcional ausente; estrutura inesperada (drift).

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

**Seletores/estratégia de extração**: mesmo gap de pesquisa do Nível A — a estrutura da página de navegação por spec entry ainda não foi verificada contra fixture real. Cada `ManifestGroupRef.source_url` (URL da página de detalhe de um grupo) é o dado-chave a extrair; **essa URL é a mesma usada por `extract_category_and_group_from_url()`** (ver Nível C abaixo) para obter `category_slug`/`group_id` de forma consistente entre os dois níveis.

**Fixtures previstas** (tasks.md): manifesto com múltiplas categorias/grupos; `group_id` duplicado dentro da mesma categoria (critical_error); manifesto truncado (`manifest_complete = False`); estrutura inesperada (drift).

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
