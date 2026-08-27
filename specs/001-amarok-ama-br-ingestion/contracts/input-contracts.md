# Contrato: Entrada raw e validação de captura

**Feature**: `001-amarok-ama-br-ingestion` — ver [../data-model.md](../data-model.md) para as entidades referenciadas.

## 1. Input Raw Capture

Contrato de entrada para o núcleo (`ingestion/`). Todo mecanismo de aquisição (manual/browser-in-the-loop nesta feature; qualquer transporte automatizado em feature futura) DEVE produzir exatamente esta forma para entregar ao núcleo — satisfazendo FR-034.

```
RawCaptureInput:
  capture_kind: "MARKET_INDEX" | "SPEC_NAVIGATION" | "GROUP_DETAIL"   # NOVO — obrigatório (research.md §16)
  source_url: str                        # obrigatório, não vazio
  collected_at: datetime (UTC)            # obrigatório
  acquisition_mode: "MANUAL_BROWSER"      # único valor válido nesta feature
  raw_content: bytes                      # obrigatório, conteúdo bruto tal como recebido
  expected_identity_context: SpecIdentity parcial | null   # opcional
  collection_metadata: dict[str, str]     # opcional
  run_id: str (UUID)                      # obrigatório — associa a um CollectionRun existente
```

`capture_kind` determina o roteamento para um dos três parsers (`contracts/domain-contracts.md`, research.md §16): `MARKET_INDEX` → `parse_market_spec_index()`; `SPEC_NAVIGATION` → `parse_spec_group_manifest()`; `GROUP_DETAIL` → `parse_group_detail()`.

**Nota sobre granularidade real de captura (corrigida — research.md §16)**: uma `RawCaptureInput` de `GROUP_DETAIL` corresponde **tipicamente a um único `Group`** — evidência de URL: `.../<spec>/<category_slug>/<group_id>` (ex.: `.../s1bc3x-56087/front-axle-steering/407`). Essa é a suposição central de design, substituindo a formulação anterior ("uma captura cobre a spec entry inteira"), que estava incorreta. O checkpoint hierárquico (data-model.md §11) continua rastreando progresso por `Group`; `CheckpointEntry.raw_capture_id` permanece capaz de ser compartilhado por múltiplos grupos caso uma captura futura venha a agregá-los, mas isso não é mais assumido como o caso comum.

**Pré-condições**:
- `raw_content` não pode ser vazio (bytes de tamanho zero são rejeitados antes mesmo da validação — tratado como `INVALID`, não como `INCOMPLETE`).
- `source_url` deve ser uma URL absoluta.
- `capture_kind` deve ser um dos três valores listados.

**Pós-condição**: ao aceitar um `RawCaptureInput`, o núcleo grava, ANTES de qualquer validação de conteúdo ou parsing (Constitution §4: "dados brutos devem ser preservados antes de adaptação"), usando os *ports* `RawBlobStore`/`RawCaptureRepository` (ver `contracts/ports-contract.md` — o núcleo não conhece a implementação concreta de armazenamento nesta etapa):
1. um `RawBlob` (data-model.md §4a) para `content_hash = sha256(raw_content)` — **somente se** este `content_hash` ainda não existir fisicamente; se já existir (mesmo conteúdo já visto antes, possivelmente em outra run), o `RawBlob` existente é reaproveitado, nenhuma cópia física duplicada é gravada;
2. uma nova `RawCapture` (Observation — data-model.md §4b) com `capture_id` **sempre novo**, referenciando o `content_hash` acima — **mesmo quando o `RawBlob` já existia**, uma nova `RawCapture` distinta é sempre criada para registrar esta observação específica (`run_id`, `collected_at`, proveniência próprios). Duas `RawCapture` nunca são colapsadas por compartilharem `content_hash` (data-model.md §4b, §13b).

A preservação do raw (ambas as gravações acima) não depende do resultado da validação subsequente.

## 2. Resultado de validação de captura

Toda `RawCapture` aceita passa pela camada `validation/`, que produz um `CaptureValidationResult` distinguindo explicitamente o outcome escolhido (`primary_outcome`) dos sinais brutos detectados (`evidence`) — **nenhum sinal detectado é descartado só porque não "venceu"**:

```
CaptureValidationResult:
  primary_outcome: "ACCEPTED" | "CHALLENGE" | "TRANSLATION_CONTAMINATED" | "INVALID" | "INCOMPLETE"
  evidence: dict                          # TODOS os sinais detectados, não apenas o que determinou primary_outcome
                                           # ex.: {"challenge_detected": true, "invalid_structure_detected": true, ...}
  detected_at: datetime
```

### Regras de detecção por sinal (contrato de comportamento — detectores concretos são item de TASKS)

Cada sinal é detectado de forma independente e registrado em `evidence`, esteja ou não ele determinando o `primary_outcome`:

| Sinal | Quando é detectado |
|---|---|
| `challenge_detected` | Sinais de CAPTCHA, Cloudflare ou página de verificação tipo "Just a moment". |
| `translation_contaminated_detected` | Sinais de tradução automática do navegador no DOM (ex.: atributos/classes injetados por extensões de tradução). |
| `invalid_structure_detected` | HTML malformado ao ponto de não ser parseável de forma confiável, ou estrutura fundamentalmente incompatível com o parser do `capture_kind` correspondente (drift estrutural — ver `contracts/domain-contracts.md`). |
| `incomplete_detected` | A captura é estruturalmente válida mas não cobre o necessário para o estágio exigido (ex.: página truncada, captura parcial deliberada). |

### DEC-003 — Precedência determinística de `primary_outcome` (aprovada pelo PO em 2026-08-26)

Quando múltiplos sinais coexistem na mesma captura, `primary_outcome` é determinado pela seguinte ordem de precedência, da mais alta para a mais baixa (ver `spec.md` §Decisions e `research.md` §20 para a decisão completa):

1. `CHALLENGE` — precedência máxima: exige human-in-the-loop e nunca pode ser mascarado por outro problema (FR-011).
2. `TRANSLATION_CONTAMINATED` — prevalece sobre `INVALID`/`INCOMPLETE` porque o DOM deixa de ser source truth confiável.
3. `INVALID` — prevalece sobre `INCOMPLETE` quando a estrutura é incompatível com o parser.
4. `INCOMPLETE` — só se aplica quando a captura é estruturalmente válida, porém parcial.
5. `ACCEPTED` — somente quando nenhum sinal anterior foi detectado.

```
primary_outcome = CHALLENGE                          se challenge_detected
                 = TRANSLATION_CONTAMINATED           senão se translation_contaminated_detected
                 = INVALID                            senão se invalid_structure_detected
                 = INCOMPLETE                          senão se incomplete_detected
                 = ACCEPTED                            caso contrário
```

**Exemplo**: `challenge_detected=true` e `invalid_structure_detected=true` simultaneamente → `primary_outcome = CHALLENGE`; `evidence` preserva os dois sinais (`{"challenge_detected": true, "invalid_structure_detected": true}`).

**Invariante**: somente `primary_outcome == ACCEPTED` segue para o parser do `capture_kind` correspondente. Os demais quatro valores são terminais para aquela captura (não geram `SpecSnapshot` em estado `VALID`, nem manifesto autoritativo, nem `DiscoveredSpecEntry` aceita) e são roteados: `CHALLENGE` → sinalização human-in-the-loop (FR-011); os demais → registrados como evidência/erro (FR-009) sem bloquear o restante da execução (uma captura inválida não aborta a run inteira). `ACCEPTED` nunca é o resultado com conteúdo vazio — a ausência de qualquer sinal negativo, não a ausência de conteúdo, é o que autoriza `ACCEPTED`.

**Rastreabilidade**: FR-001 (via `MARKET_INDEX`/`SPEC_NAVIGATION`), FR-008, FR-009, FR-010, FR-011, SC-003; DEC-003.
