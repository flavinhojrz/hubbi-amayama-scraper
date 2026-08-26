# Contrato: Entrada raw e validação de captura

**Feature**: `001-amarok-ama-br-ingestion` — ver [../data-model.md](../data-model.md) para as entidades referenciadas.

## 1. Input Raw Capture

Contrato de entrada para o núcleo (`ingestion/`). Todo mecanismo de aquisição (manual/browser-in-the-loop nesta feature; qualquer transporte automatizado em feature futura) DEVE produzir exatamente esta forma para entregar ao núcleo — satisfazendo FR-034.

```
RawCaptureInput:
  source_url: str                        # obrigatório, não vazio
  collected_at: datetime (UTC)            # obrigatório
  acquisition_mode: "MANUAL_BROWSER"      # único valor válido nesta feature
  raw_content: bytes                      # obrigatório, conteúdo bruto tal como recebido
  expected_identity_context: SpecIdentity parcial | null   # opcional
  collection_metadata: dict[str, str]     # opcional
  run_id: str (UUID)                      # obrigatório — associa a um CollectionRun existente
```

**Nota sobre checkpoint hierárquico** (data-model.md §11): uma única `RawCaptureInput` tipicamente cobre uma spec entry inteira (múltiplas `Category`/`Group`/`Schema`), dado que a aquisição é manual/browser-in-the-loop por página (DEC-001). Após parsing, cada `Group` extraído dessa captura recebe seu próprio `CheckpointEntry`, todos podendo referenciar o mesmo `capture_id` — o checkpoint rastreia progresso de *processamento* por `Group`, não exige uma captura por grupo.

**Pré-condições**:
- `raw_content` não pode ser vazio (bytes de tamanho zero são rejeitados antes mesmo da validação — tratado como `INVALID`, não como `INCOMPLETE`).
- `source_url` deve ser uma URL absoluta.

**Pós-condição**: ao aceitar um `RawCaptureInput`, o núcleo grava, ANTES de qualquer validação de conteúdo ou parsing (Constitution §4: "dados brutos devem ser preservados antes de adaptação"):
1. um `RawBlob` (data-model.md §4a) para `content_hash = sha256(raw_content)` — **somente se** este `content_hash` ainda não existir fisicamente; se já existir (mesmo conteúdo já visto antes, possivelmente em outra run), o `RawBlob` existente é reaproveitado, nenhuma cópia física duplicada é gravada;
2. uma nova `RawCapture` (Observation — data-model.md §4b) com `capture_id` **sempre novo**, referenciando o `content_hash` acima — **mesmo quando o `RawBlob` já existia**, uma nova `RawCapture` distinta é sempre criada para registrar esta observação específica (`run_id`, `collected_at`, proveniência próprios). Duas `RawCapture` nunca são colapsadas por compartilharem `content_hash` (data-model.md §4b, §13b).

A preservação do raw (ambas as gravações acima) não depende do resultado da validação subsequente.

## 2. Resultado de validação de captura

Toda `RawCapture` aceita passa pela camada `validation/`, que produz exatamente um dos cinco resultados a seguir (mutuamente exclusivos — research.md §13):

```
CaptureValidationResult:
  outcome: "ACCEPTED" | "CHALLENGE" | "TRANSLATION_CONTAMINATED" | "INVALID" | "INCOMPLETE"
  evidence: dict                          # sinais que levaram à decisão (ex.: strings detectadas, seletores ausentes)
  detected_at: datetime
```

### Regras de classificação (contrato de comportamento — detectores concretos são item de TASKS)

| Outcome | Quando se aplica |
|---|---|
| `ACCEPTED` | Estrutura mínima esperada (conforme `contracts/domain-contracts.md` §"Seletores v1") está presente e nenhum sinal de challenge/tradução/HTML inválido foi detectado. |
| `CHALLENGE` | Sinais de CAPTCHA, Cloudflare ou página de verificação tipo "Just a moment" foram detectados. **Nunca** classificado como `ACCEPTED` com conteúdo vazio — challenge é sempre `CHALLENGE`, nunca uma "página vazia válida". |
| `TRANSLATION_CONTAMINATED` | Sinais de tradução automática do navegador no DOM (ex.: atributos/classes injetados por extensões de tradução) foram detectados. |
| `INVALID` | HTML malformado ao ponto de não ser parseável de forma confiável, ou estrutura fundamentalmente incompatível com o parser v1 (drift estrutural — ver `contracts/domain-contracts.md`). |
| `INCOMPLETE` | A captura é estruturalmente válida mas não cobre o necessário para o estágio exigido (ex.: página truncada, captura parcial deliberada). |

**Invariante**: somente `ACCEPTED` segue para `parsing/`. Os demais quatro resultados são terminais para aquela captura (não geram `SpecSnapshot` em estado `VALID`) e são roteados: `CHALLENGE` → sinalização human-in-the-loop (FR-011); os demais → registrados como evidência/erro (FR-009) sem bloquear o restante da execução (uma captura inválida não aborta a run inteira).

**Rastreabilidade**: FR-008, FR-009, FR-010, FR-011, SC-003.
