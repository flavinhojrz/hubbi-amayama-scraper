# Contrato: Domínio parseado (parser → raw domain model)

**Feature**: `001-amarok-ama-br-ingestion` — ver [../data-model.md](../data-model.md) para os tipos de entidade completos.

## Seletores v1 (contrato de parser, não implementação)

Evidência técnica já pesquisada. O parser v1 (`parsing/`) DEVE usar exatamente estes seletores como contrato inicial; qualquer divergência estrutural encontrada em runtime DEVE produzir um erro explícito de drift (nunca parsing permissivo que oculte a divergência — ponto 20 do PLAN):

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

**Gap de pesquisa conhecido (não bloqueante)**: nenhum seletor de "categoria" foi pesquisado/fornecido até o momento — apenas os níveis de schema/tabela de peças. O contrato de parsing v1 ainda exige a resolução de `Category.category_slug` (Constitution §2, ponto 6 do PLAN), mas a forma exata de extraí-la (URL, breadcrumb, atributo de página) fica como item de pesquisa a resolver em TASKS/implementação, sem impacto em requisito, escopo ou identidade — apenas um detalhe de extração ainda não coberto pela pesquisa de seletores.

## Resultado de parsing por unidade

Parsing produz, para cada spec entry `ACCEPTED`, uma árvore de domínio bruta:

```
ParsedSpecEntry:
  identity: SpecIdentity                        # ver data-model.md §1
  categories: list[ParsedCategory]
  parse_errors: list[ParseError]                 # erros não-críticos (não abortam a spec entry inteira)
  critical_error: ParseError | null              # presente ⇒ resultado tratado como INVALID, não gera snapshot VALID

ParsedCategory:
  category_slug: str
  groups: list[ParsedGroup]

ParsedGroup:
  group_id: str                                  # string, preserva zeros à esquerda — nunca int
  schemas: list[ParsedSchema]                     # pode ser vazio — grupo vazio é válido e preservado

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

**Invariante de invariante estrutural — `group_id` duplicado**: se dois `ParsedGroup` no mesmo `ParsedCategory` compartilham `group_id`, isso é um `critical_error` para aquela categoria (nunca uma sobrescrita silenciosa — ponto 6 do PLAN). O restante da spec entry (outras categorias) pode continuar sendo processado; a categoria afetada é marcada como não confiável.

**Rastreabilidade**: FR-002, FR-013, FR-014, edge case "campo opcional ausente", edge case "duplicate group_id".
