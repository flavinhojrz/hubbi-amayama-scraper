# Phase 1 Data Model: MVP de Ingestão Amayama — Volkswagen Amarok (Mercado AMA BR)

**Feature**: `001-amarok-ama-br-ingestion` | **Date**: 2026-08-25 | **Spec**: [spec.md](./spec.md) | **Research**: [research.md](./research.md)

Este documento descreve entidades e invariantes de domínio. Não é código: é o contrato que `tasks.md`/implementação devem seguir. Tipos são indicados de forma conceitual (ex.: `str`, `date | None`), não como assinaturas finais de classe.

## Visão geral da hierarquia

```
Model (Amarok)
  └─ Market (AMA BR)
       └─ Spec Entry (identidade: SpecIdentity)
            └─ Category
                 └─ Group
                      └─ Schema
                           └─ Part (contém oem_code)
                                └─ OemReference (projeção derivada — ver research.md §11)
```

---

## 1. `SpecIdentity`

Identidade de uma spec entry. Nunca depende apenas de `model_code` (FR-003, Constitution §2).

| Campo | Tipo | Obrigatório | Notas |
|---|---|---|---|
| `source` | `str` | sim | Constante `"AMAYAMA"` nesta feature (Constitution §2). |
| `manufacturer` | `str` | sim | Constante `"VOLKSWAGEN"` nesta feature. |
| `vehicle_model` | `str` | sim | Constante `"AMAROK"` nesta feature. |
| `market` | `str` | sim | Constante `"AMA-BR"` nesta feature. |
| `model_code` | `str` | sim | Não é único isoladamente (FR-003). |
| `amayama_catalog_id` | `str` | sim | Participa da identidade (Constitution §2). |
| `production_period_raw` | `str` | sim | Texto de período preservado verbatim da fonte. |
| `production_start` | `date \| None` | não | Melhor esforço, extraído de `production_period_raw` quando parseável; ausência não é erro. |
| `production_end` | `date \| None` | não | Idem; `None` também representa "em produção"/open-ended quando comprovado pela fonte. |
| `grade` | `str \| None` | não | Somente quando comprovado pela fonte (FR-005). |
| `configuration` | `str \| None` | não | Somente quando comprovado pela fonte (FR-005). |
| `source_url` | `str` | sim | URL de origem da spec entry. |

**Identidade normativa**: a tupla explícita `(source, manufacturer, vehicle_model, market, model_code, amayama_catalog_id)` — os seis campos permanecem individualmente presentes em `SpecIdentity` (nunca apenas embutidos em uma string). `production_start`, `production_end` e `source_url` **não** participam da identidade normativa nem do `stable_key` (ver justificativa em research.md §10) — podem mudar sem representar uma nova spec entry.

**Campos derivados** (ver research.md §10 para o algoritmo completo):
- `stable_key`: hash determinístico (`SHA256("amayama:spec-identity:v1\0" + canonical_json(...))`) sobre os seis campos da identidade normativa, já normalizados. Usado para correlação entre execuções e como critério de desempate na seleção de representante (FR-022) — nunca como chave primária de linha (surrogate id separado é usado para isso).
- `display_key`: representação legível (`f"{source}:{market}:{model_code}:{amayama_catalog_id}"`, com escaping de `:`/`\` por componente) usada exclusivamente para logs/depuração — nunca para igualdade, lookup ou desempate.

**Invariantes**:
- Duas `SpecIdentity` com `amayama_catalog_id` diferentes NUNCA são a mesma spec entry, mesmo com `model_code` idêntico (FR-003, SC-002, SC-006) — refletido em `stable_key` diferentes.
- `grade`/`configuration` ausentes não invalidam a identidade (FR-005).
- Uma mudança em `production_start`/`production_end`/`source_url` nunca altera `stable_key` (research.md §10).

---

## 2. `Category`, `Group`, `Schema`

| Entidade | Campos-chave | Invariantes |
|---|---|---|
| `Category` | `category_slug: str`, `spec_identity_ref` | Único por `(spec_identity, category_slug)`. |
| `Group` | `group_id: str` (preservado como string — nunca `int`, para não perder zeros à esquerda), `category_ref` | `group_id` duplicado dentro do mesmo escopo (`category_ref`) é **erro/invariante violado**, nunca sobrescrita silenciosa (ponto 6 do PLAN) — a violação deve ser reportada como erro de captura/parsing, não silenciada. Grupos vazios (sem `Schema`/`Part` associado) são válidos e devem ser preservados como tal, distintos de "grupo não encontrado". |
| `Schema` | `schema_id: str` (trim), `group_ref` | Possui `schema_semantic_hash` próprio (ver `fingerprints`), independente de `parts_hash`/`image_hash`. |

---

## 3. `Part`

Peça associada a um `Schema`, com os campos do ponto 7 do PLAN / FR-013.

| Campo | Tipo | Obrigatório | Notas |
|---|---|---|---|
| `schema_id` | `str` | sim | Referência ao `Schema` pai (redundante por conveniência de fingerprint — ver `fingerprints`). |
| `position_pnc` | `str` | sim | PNC/posição; trim + uppercase na normalização. |
| `oem_code` | `str \| None` | não | Ausência legítima ≠ erro (FR-014). Uppercase + remoção de whitespace técnico na normalização. |
| `description` | `str \| None` | não | |
| `details` | `str \| None` | não | |
| `period_application_text` | `str \| None` | não | Texto verbatim (não parseado para datas — ao contrário de `production_period_raw` da spec entry, que tem parsing best-effort; aqui não há esse requisito). |
| `pr_codes` | `list[str]` | não (lista pode ser vazia) | Uppercase + ordenados quando forem lista estruturada (regra de normalização, item 9). |
| `quantity` | `str \| None` | não | Preservado como veio da fonte (pode não ser puramente numérico — ex. "1x"); parsing numérico é decisão de TASKS, não obrigação desta PLAN. |
| `image_url` | `str \| None` | não | Usado para resolução em `Image`/`ResolvedImage`, não é o fingerprint de imagem em si. |

**Invariantes**:
- Um campo opcional ausente **não invalida** a peça (FR-014). Uma peça só é rejeitada por **erro de parsing** (estrutura inesperada onde um campo era esperado e o parser não conseguiu extrair de forma confiável) — a distinção entre "campo ausente" e "erro de parsing" deve ser explícita no resultado de parsing (ver `contracts/domain-contracts.md`).
- `Part.oem_code` não deve ser confundido com o nó hierárquico `OemReference` (ver research.md §11).

**Não inferir** (ponto 7 do PLAN / FR-006): nenhum campo de `body`, `engine`, `drivetrain`, `transmission` existe neste modelo — esses atributos simplesmente não são capturados/derivados nesta feature.

---

## 4. `RawBlob` e `RawCapture` (Observation)

**Distinção normativa (correção de idempotência)**: content-addressing deduplica **bytes físicos**, não **eventos de coleta**. Duas capturas realizadas em momentos/runs distintos podem produzir exatamente o mesmo `content_hash` — o blob físico é compartilhado, mas as duas observações permanecem entidades distintas, cada uma com sua própria proveniência. Por isso o domínio separa explicitamente duas entidades:

### 4a. `RawBlob` (conteúdo físico, content-addressed)

| Campo | Tipo | Obrigatório | Notas |
|---|---|---|---|
| `content_hash` | `str` (sha256 hex) | sim (chave) | Hash de `raw_content`; também é a chave do armazenamento content-addressed (research.md §8). Chave primária de `RawBlob` — não se repete fisicamente. |
| `size_bytes` | `int` | sim | Tamanho do conteúdo, para auditoria/inspeção rápida sem ler o arquivo. |
| `storage_path` | `str` | sim | Caminho no filesystem content-addressed (derivado deterministicamente de `content_hash`). |
| `first_seen_at` | `datetime` (UTC) | sim | Momento em que este conteúdo físico foi gravado pela primeira vez — **não** é o `collected_at` de nenhuma observação específica, é metadado do blob em si. |

`RawBlob` não tem `run_id`, `collected_at` "de negócio" nem proveniência de coleta — essas informações pertencem exclusivamente a `RawCapture`. Um `RawBlob` pode ser referenciado por múltiplas `RawCapture` (mesmo conteúdo, observações diferentes).

### 4b. `RawCapture` (Observation — evento de coleta com identidade própria)

Entrada adquirida externamente (browser-in-the-loop manual, nesta feature — DEC-001), independente do mecanismo de aquisição (FR-034).

| Campo | Tipo | Obrigatório | Notas |
|---|---|---|---|
| `capture_id` | `str` (UUID) | sim | Identidade própria da observação — **nunca** derivada de `content_hash`. Duas capturas com o mesmo `content_hash` recebem `capture_id` distintos. |
| `run_id` | `str` (UUID) | sim | Referência à `CollectionRun` (checkpoint/resume). Parte da proveniência da observação. |
| `content_hash` | `str` (sha256 hex) | sim | Referência (FK conceitual) ao `RawBlob` correspondente — **não** é a identidade da observação, é a identidade do conteúdo que ela capturou. |
| `source_url` | `str` | sim | |
| `collected_at` | `datetime` (UTC) | sim | Momento desta observação específica — distinto de `RawBlob.first_seen_at` quando o mesmo conteúdo é reobservado depois. |
| `acquisition_mode` | `enum {MANUAL_BROWSER}` | sim | Único valor válido nesta feature (DEC-001); campo existe para que o núcleo permaneça agnóstico e a automação futura só precise adicionar um novo valor de enum, não alterar o contrato (FR-034). |
| `expected_identity_context` | `SpecIdentity parcial \| None` | não | O que se esperava encontrar (ex.: `model_code`/`market` presumidos pela navegação), para permitir detectar divergência entre o esperado e o efetivamente parseado. |
| `collection_metadata` | `dict[str, str]` | não | Metadados livres de coleta (ex.: nota do operador humano). |

**Invariantes**:
- `RawBlob` e `RawCapture` são ambos imutáveis após criação (Constitution §4). Nenhuma transformação (parsing, normalização) modifica qualquer um dos dois — apenas lê a partir deles.
- **Duas `RawCapture` com o mesmo `content_hash` NUNCA são colapsadas em uma única observação.** `run_id`, `collected_at`, `capture_id` e proveniência permanecem distintos mesmo quando o `RawBlob` referenciado é o mesmo (satisfaz o requisito de não perder provenance quando duas observações compartilham o mesmo raw hash).
- Gravar uma nova `RawCapture` cujo conteúdo já existe como `RawBlob` **não** grava um novo blob físico (reaproveita o `RawBlob` existente por `content_hash`) — apenas insere uma nova linha de `RawCapture` referenciando-o. Gravar conteúdo inédito cria um novo `RawBlob` e uma nova `RawCapture` na mesma operação lógica.

---

## 5. Resultado de validação de captura

Ver `contracts/input-contracts.md` para o contrato completo. Resumo do tipo:

`CaptureValidationResult = ACCEPTED | CHALLENGE | TRANSLATION_CONTAMINATED | INVALID | INCOMPLETE`

Mutuamente exclusivos (research.md §13). Somente `ACCEPTED` segue para parsing.

---

## 6. `SpecSnapshot`

| Campo | Tipo | Obrigatório | Notas |
|---|---|---|---|
| `snapshot_id` | `str` (UUID) | sim | |
| `spec_identity_ref` | `str` (`stable_key` hash ou surrogate id) | sim | |
| `idempotency_key` | `str` (sha256 hex) | sim | **Chave única** (constraint `UNIQUE(idempotency_key)`). Impede que um retry da mesma finalização crie um `SpecSnapshot` duplicado — ver §13 para o algoritmo completo. |
| `collected_at` | `datetime` | sim | Herdado da `RawCapture` de origem mais recente entre as aceitas para este snapshot. |
| `parser_version` | `str` | sim | Ex.: `amayama-parser-v1`. |
| `normalizer_version` | `str` | sim | Ex.: `amayama-normalizer-v1`. |
| `fingerprint_version` | `str` | sim | Ex.: `amayama-fingerprint-v1`. |
| `collection_complete` | `bool` | sim | Derivado do estado agregado dos `CheckpointEntry` (§11) daquela spec entry: `True` se e somente se todos os `Group` descobertos para a spec entry têm status `ACCEPTED`; `False` caso exista ao menos um `Group` `PENDING`/`IN_PROGRESS`/`REJECTED`. Checkpoint `ACCEPTED` em todos os grupos é precondição necessária, mas a avaliação de completude (o que conta como "todos os grupos esperados") é decisão de TASKS/implementação sobre como a descoberta de grupos é considerada encerrada para aquela spec entry. |
| `structure_hash` | `str` (sha256 hex) | sim | Ver `fingerprints`. |
| `spec_parts_hash` | `str` (sha256 hex) | sim | Ver `fingerprints`. |
| `schema_semantic_hash` | `str` (sha256 hex) | sim | Ver `fingerprints`. |
| `image_hash` | `str` (sha256 hex) | sim | Ver `fingerprints`. |
| `counts` | `dict[str, int]` | sim | Evidência de auditoria (ex.: `{"parts": 42, "groups": 5, "categories": 2}`). |
| `state` | `enum {VALID, INCOMPLETE, STALE, SUPERSEDED, INVALID}` | sim | Ver máquina de estados abaixo. |

**Máquina de estados** (ponto 17 do PLAN — mantida simples, sem transições implícitas):

```
        collection_complete=true, sem erro crítico
CAPTURE ─────────────────────────────────────────► VALID
        │
        │ collection_complete=false OU captura parcial exigida pelo estágio
        └───────────────────────────────────────────► INCOMPLETE

        (evento externo: revalidação detecta divergência de conteúdo
         na fonte, sem nova captura ainda realizada)
VALID ──────────────────────────────────────────────► STALE

        (nova captura aceita para a mesma spec entry, gerando snapshot mais novo)
VALID/STALE ─────────────────────────────────────────► SUPERSEDED
        (o snapshot antigo transita para SUPERSEDED; o novo nasce VALID/INCOMPLETE)

        captura rejeitada pela validação (challenge/tradução/inválida)
CAPTURE ─────────────────────────────────────────────► INVALID
```

**Invariantes**:
- `INCOMPLETE` e `INVALID` nunca participam de avaliação de equivalência (FR-028).
- Reprocessamento sempre cria um novo `SpecSnapshot`; o anterior transita para `SUPERSEDED` (quando havia um `VALID`/`STALE` anterior), nunca é apagado ou sobrescrito (FR-029, SC-008). Uma falha de nova coleta (ex.: nova captura vira `INVALID`) não apaga nem transiciona o último `VALID` conhecido — o "last-known-good" permanece `VALID` até uma nova captura **bem-sucedida** o suceder.
- Mudança isolada em `image_hash` não afeta `spec_parts_hash` nem move a spec para outro cluster (FR-030, SC-009) — os quatro hashes são campos independentes por construção (ver `fingerprints`).

---

## 7. `FingerprintSet` (hierárquico)

Ver `contracts/normalization-fingerprint-contracts.md` para os algoritmos/serialização. Resumo estrutural:

```
part_fingerprint (por Part)
  → group_fingerprint (multiset de part_fingerprint do Group, preserva contagem)
    → category_fingerprint (multiset de group_fingerprint da Category, inclui grupos vazios)
      → spec_parts_hash (multiset de category_fingerprint da Spec Entry)
```

Em paralelo, e de forma **independente**:
- `schema_semantic_hash`: deriva do conjunto de `Schema` (estrutura semântica), não do conteúdo de `Part`.
- `image_hash`: deriva do conjunto de imagens (`ResolvedImage.own`), nunca entra em `spec_parts_hash`.
- `structure_hash`: deriva da forma estrutural bruta (contagem/organização de categories/groups/schemas), útil para revalidação incremental localizar nível de divergência antes de recomputar hashes de conteúdo.

**Invariante**: comparação de coleções em qualquer nível é por **multiset** (ordem não importa; duplicatas alteram o resultado) — nunca por conjunto (set) nem por lista ordenada.

---

## 8. `EquivalenceResult`

| Campo | Tipo | Notas |
|---|---|---|
| `parts_relation` | `enum {EXACT, DIFFERENT, UNKNOWN}` | |
| `schema_relation` | `enum {EXACT, DIFFERENT, UNKNOWN}` | |
| `image_relation` | `enum {EXACT, COMPLEMENTARY, DIFFERENT, NONE, UNKNOWN}` | |
| `comparison_valid` | `bool` | Ver condições de validade em `contracts/equivalence-contracts.md`. |

**Invariante central**: deduplicação só ocorre quando `comparison_valid AND parts_relation == EXACT` (Constitution §8, FR-019). Divergência de versão (`normalizer_version`/`fingerprint_version` incompatíveis entre os dois lados) produz `comparison_valid=False` e `parts_relation=UNKNOWN` — nunca `DIFFERENT`.

---

## 9. `EquivalenceClass` (cluster) e `ClusterAssignment`

| Campo | Tipo | Notas |
|---|---|---|
| `cluster_key` | `str` | Derivado de `scope + normalizer_version + fingerprint_version + spec_parts_hash` (Constitution §9). |
| `scope` | `str` | Fixo nesta feature: `AMAYAMA:VOLKSWAGEN:AMAROK:AMA-BR` (research.md, ponto 13 do PLAN). |
| `representative_spec_ref` | `str` | Selecionado deterministicamente (ver research.md §12). |
| `member_spec_refs` | `list[str]` | Todas as specs do cluster, incluindo o representante; nenhuma perde identidade/aplicabilidade (FR-021). |

**Invariante**: o `cluster_key` é a fonte normativa da equivalência. Uma estrutura auxiliar tipo DSU/Union-Find, se usada futuramente para performance de agrupamento incremental, nunca é a fonte de verdade — apenas um índice derivado, recomputável a partir de `cluster_key` (ponto 14 do PLAN).

`ClusterAssignment` é o registro persistido de qual `spec_identity` pertence a qual `cluster_key`, versionado por `normalizer_version`/`fingerprint_version` (uma mudança de versão invalida assignments antigos para recomputação, nunca os reinterpreta como equivalentes entre versões incompatíveis).

---

## 10. `ResolvedImage`

| Campo | Tipo | Notas |
|---|---|---|
| `part_ref` ou `spec_identity_ref` | `str` | A que a imagem resolvida se aplica. |
| `origin_spec_ref` | `str` | Spec entry de onde a imagem **realmente** veio (própria ou fallback). |
| `is_fallback` | `bool` | `False` quando é imagem própria; `True` quando herdada de outro membro do cluster. |
| `image_url_or_ref` | `str` | |
| `resolved_within_cluster_key` | `str \| None` | Obrigatório quando `is_fallback=True` — o cluster que comprovou a equivalência que autorizou o fallback (FR-023). |

**Invariantes**:
- Fallback só é permitido quando `is_fallback=True` está associado a um `resolved_within_cluster_key` válido, cujo `parts_relation == EXACT` (FR-023).
- `origin_spec_ref` nunca é omitido/inferido silenciosamente (FR-024, FR-025).

---

## 11. `CollectionRun` / `CheckpointEntry` (hierárquico — revisado por decisão técnica do PO)

Checkpoint é hierárquico (research.md §9 — decisão revisada):

```
Collection Run
  ↓
Spec Entry
  ↓
Category
  ↓
Group   ← unidade mínima de progresso retomável
```

### `CollectionRun`

| Campo | Tipo | Notas |
|---|---|---|
| `run_id` | `str` (UUID) | |
| `scope` | `str` | Mesmo `scope` da equivalência (research.md ponto 13). |
| `started_at` / `resumed_at` / `completed_at` | `datetime \| None` | |

### `CheckpointEntry`

Unidade mínima de progresso retomável. **Chave única (constraint)**: `UNIQUE(run_id, spec_key, category_slug, group_id)` — no máximo um `CheckpointEntry` lógico existe por unidade de progresso dentro do mesmo run; um surrogate id de linha pode existir para conveniência de storage, mas nunca permite uma segunda linha para a mesma chave. Toda escrita em `CheckpointEntry` é uma operação de **upsert idempotente** sobre essa chave — ver §13 para o algoritmo completo.

| Campo | Tipo | Obrigatório | Notas |
|---|---|---|---|
| `run_id` | `str` (UUID) | sim | Referência à `CollectionRun`. |
| `spec_key` | `str` | sim | `stable_key` (§1) da `SpecIdentity` sendo coletada — ou o melhor identificador disponível a partir de `expected_identity_context` (§4) antes da identidade completa ser confirmada pelo parsing. |
| `category_slug` | `str` | sim | Usado como agrupamento/índice de `group_id` — evita colisão de `group_id` entre categorias distintas (consistente com a invariante de §2). Não é, por si só, uma unidade de status separada. |
| `group_id` | `str` | sim | Preservado como string (zeros à esquerda) — mesma regra de §2. |
| `status` | `enum {PENDING, IN_PROGRESS, ACCEPTED, REJECTED}` | sim | Ver regras de transição abaixo. |
| `raw_capture_id` | `str \| None` | não | Referência ao `RawCapture` (§4) associado a esta tentativa. Como uma única captura de página tipicamente contém múltiplos `Group`s (ver seletores em `contracts/domain-contracts.md`), o mesmo `raw_capture_id` pode ser referenciado por múltiplos `CheckpointEntry` da mesma spec entry. |
| `attempt_count` | `int` | sim | Incrementado a cada nova tentativa de processar este `Group` (inclusive revalidação deliberada). |
| `last_attempt_at` | `datetime \| None` | não | |
| `completed_at` | `datetime \| None` | não | Preenchido somente quando `status == ACCEPTED`. |
| `evidence` | `dict \| None` | não | Erro/evidência quando `status == REJECTED` (ex.: `critical_error` de parsing, outcome de validação que motivou a rejeição). |

**Regras de transição**:
- `PENDING → IN_PROGRESS`: início de uma tentativa de processar o `Group` a partir de uma captura `ACCEPTED` (contracts/input-contracts.md).
- `IN_PROGRESS → ACCEPTED`: o `Group` foi parseado sem `critical_error` e persistido com sucesso.
- `IN_PROGRESS → REJECTED`: qualquer falha — parsing com `critical_error` para aquele grupo, ou a captura de origem não é `ACCEPTED` (é `CHALLENGE`, `TRANSLATION_CONTAMINATED`, `INVALID` ou `INCOMPLETE`). **Challenge/CAPTCHA/Cloudflare, captura inválida ou incompleta NUNCA transicionam um `Group` para `ACCEPTED`** — apenas para `REJECTED` (ou permanecem `PENDING` se a tentativa nem chegou a ocorrer).
- `REJECTED → IN_PROGRESS`: nova tentativa (retry manual ou nova captura), incrementando `attempt_count`.
- Não existe transição para fora de `ACCEPTED` dentro da mesma run — um `Group` `ACCEPTED` é definitivo para efeitos daquela `CollectionRun` (uma revalidação futura opera como uma nova run/tentativa, não reabre o checkpoint antigo).

**Invariantes**:
- Um `Group` com `status == ACCEPTED` e persistido não precisa ser recoletado/reprocessado após uma interrupção (retomada consulta apenas `Group`s `PENDING`/`IN_PROGRESS`/`REJECTED`) — FR-012, SC-004.
- `SpecSnapshot.collection_complete` (§6) só pode ser `True` quando todos os `Group`s descobertos para aquela spec entry estão `ACCEPTED`.
- Raw já aceito permanece preservado independentemente do resultado de tentativas posteriores sobre o mesmo `Group` (Constitution §4).
- **Idempotência real** (ver §13 para o mecanismo completo — content-addressing por si só é insuficiente, apenas deduplica bytes físicos): a chave única `(run_id, spec_key, category_slug, group_id)` combinada com upsert transacional garante que repetir a mesma operação de checkpoint nunca produz uma segunda linha para a mesma unidade de progresso nem uma transição concorrente/repetida indevida para `ACCEPTED`.

**Rastreabilidade**: FR-008, FR-009, FR-012, SC-004, User Story 7, research.md §9.

---

## 12. `CurrentSpecState` (projeção)

Projeção de leitura (não fonte de verdade) que aponta, para cada `SpecIdentity`, para seu `SpecSnapshot` mais recente em estado `VALID`/`STALE` e para seu `cluster_key` atual — usada para consultas/exportação sem recomputar a partir do histórico completo a cada leitura. Reconstruível a qualquer momento a partir de `SpecSnapshot` + `ClusterAssignment` (não é uma fonte de dados independente).

---

## 13. Idempotência e atomicidade da finalização (correção técnica)

**Motivação**: content-addressing (§4a) evita duplicação **física** do blob raw, mas não evita, por si só: (a) duas linhas de checkpoint para a mesma unidade lógica; (b) duas transições concorrentes/repetidas para `ACCEPTED`; (c) dois `SpecSnapshot` gerados por um retry da mesma coleta aceita; (d) perda de provenance quando duas observações distintas compartilham o mesmo `content_hash`. Esta seção fecha essas quatro lacunas. Ver `research.md` (nova seção "Idempotência de checkpoint/snapshot e atomicidade de finalização") para o Decision/Rationale completo, e `contracts/snapshot-contract.md` para o pseudo-algoritmo executável.

### 13a. Upsert idempotente de `CheckpointEntry`

Toda escrita em `CheckpointEntry` ocorre dentro de uma transação SQLite (`BEGIN IMMEDIATE ... COMMIT`, suficiente para MVP com escritor único) e segue semântica de **insert-or-update sobre a chave única** `(run_id, spec_key, category_slug, group_id)`:

```
upsert_checkpoint(run_id, spec_key, category_slug, group_id, attempted_status, raw_capture_id, evidence):
  BEGIN IMMEDIATE
    existing = SELECT * FROM checkpoint_entry
               WHERE (run_id, spec_key, category_slug, group_id) = key
    IF existing IS NULL:
      INSERT nova linha (status=attempted_status, attempt_count=1, ...)
    ELIF existing.status == ACCEPTED:
      # no-op idempotente: um Group já ACCEPTED nunca regride nem duplica progresso
      # (uma revalidação deliberada é modelada como uma nova tentativa/ciclo, não como
      # reabertura do checkpoint ACCEPTED desta run — ver §11 "Regras de transição")
      NO-OP (retorna a linha existente inalterada)
    ELSE:
      UPDATE linha existente: status=attempted_status, attempt_count+=1,
             last_attempt_at=now, completed_at=(now se ACCEPTED senão NULL),
             raw_capture_id=raw_capture_id, evidence=evidence
  COMMIT
```

Isso garante: (1) nunca mais de uma linha lógica por unidade de progresso (chave única); (2) repetir a mesma operação não produz progresso duplicado (upsert); (3) uma vez `ACCEPTED`, a linha é terminal para a run — uma segunda tentativa de "aceitar de novo" é um no-op, nunca uma segunda transição.

### 13b. Chave de idempotência do `SpecSnapshot`

```
accepted_checkpoint_fingerprint(spec_key, run_id) =
  SHA256("amayama:checkpoint-fingerprint:v1\0" + canonical_json({
    "accepted_units_multiset": sorted(count((category_slug, group_id, raw_capture_id)) as pairs)
  }))
  # multiset sobre os CheckpointEntry com status ACCEPTED para (spec_key, run_id)
  # usa raw_capture_id (identidade da OBSERVAÇÃO), não content_hash — preserva a distinção
  # do §4: duas observações do mesmo conteúdo em momentos/runs diferentes não colapsam aqui

SpecSnapshot.idempotency_key =
  SHA256("amayama:snapshot-idempotency:v1\0" + canonical_json({
    "run_id": run_id,
    "spec_key": spec_key,
    "accepted_checkpoint_fingerprint": accepted_checkpoint_fingerprint(spec_key, run_id)
  }))
```

**Propriedades garantidas**:
- **Retry da mesma finalização não cria snapshot duplicado**: se a mesma run tenta finalizar a mesma spec entry com exatamente o mesmo conjunto de `CheckpointEntry` `ACCEPTED` (mesmos `raw_capture_id`), `idempotency_key` é idêntico — a inserção é um upsert (`INSERT ... ON CONFLICT(idempotency_key) DO NOTHING`, ver §13c), nunca uma segunda linha.
- **Uma coleta posterior legítima do mesmo spec cria NOVO snapshot**: uma nova `RawCapture` (novo `capture_id`, mesmo que reaproveite um `RawBlob` existente) usada para reaceitar um `Group` produz um `accepted_checkpoint_fingerprint` diferente (o multiset de `raw_capture_id` mudou) — logo um `idempotency_key` diferente, e um novo `SpecSnapshot` legítimo é criado, sucedendo o anterior (`SUPERSEDED`).
- **Raw igual em momentos diferentes não implica mesmo snapshot**: por construção, o fingerprint usa `raw_capture_id` (observação), não `content_hash` (blob) — dois `RawBlob` idênticos capturados como duas `RawCapture` distintas (§4b) produzem `accepted_checkpoint_fingerprint` diferentes.
- **Snapshot permanece imutável após criado**: `idempotency_key` é calculado uma única vez na criação; nenhuma atualização posterior o recalcula ou o reatribui (apenas o campo `state` transiciona — ver §6).

### 13c. Atomicidade da finalização

A transição final de uma spec entry para snapshot aceito é uma única transação de metadados:

```
finalize_spec_entry(spec_key, run_id):
  BEGIN IMMEDIATE
    1. Validar completude: consultar CheckpointEntry de (spec_key, run_id);
       determinar collection_complete (ver §6) e computar idempotency_key (§13b)
    2. IF já existe SpecSnapshot com este idempotency_key:
         → finalização já ocorreu (retry idempotente); pular para o passo 5 sem inserir nada novo
       ELSE:
         → computar structure_hash/spec_parts_hash/schema_semantic_hash/image_hash
         → INSERT novo SpecSnapshot (state = VALID ou INCOMPLETE conforme collection_complete)
    3. IF um SpecSnapshot VALID/STALE anterior existia para spec_key:
         → UPDATE seu state para SUPERSEDED
         (somente quando o passo 2 efetivamente inseriu um snapshot novo)
    4. UPDATE current_spec_state para apontar ao snapshot_id do passo 2
       (o novo, ou o já existente em caso de retry idempotente)
    5. Marcar a finalização desta spec entry como concluída nesta run
  COMMIT
```

Toda a sequência ocorre dentro de uma única transação SQLite — uma falha parcial (processo interrompido no meio) faz rollback completo: nenhum estado intermediário fica visível (nem snapshot duplicado, nem `current_spec_state` apontando para um snapshot inexistente, nem checkpoint "concluído" sem um snapshot consistente por trás). SQLite com escritor único (ou WAL com um único escritor por vez) é suficiente para este MVP — nenhum mecanismo de locking adicional é necessário; se acesso concorrente multi-processo se tornar um requisito futuro, ele é tratado na migração de `persistence/` (research.md §8), não neste desenho.

**Rastreabilidade**: FR-008, FR-009, FR-012, FR-026, FR-029, SC-004, SC-008.

---

## Resumo de rastreabilidade (entidade → FR)

| Entidade | FRs relacionados |
|---|---|
| `SpecIdentity` | FR-002 a FR-007, FR-021 |
| `RawBlob` / `RawCapture` | FR-008, FR-009, FR-034 |
| Validação de captura | FR-010, FR-011 |
| `Part` | FR-013, FR-014 |
| Normalização (ver contracts) | FR-015, FR-016 |
| `FingerprintSet` | FR-017, FR-018 |
| `EquivalenceResult` | FR-019, FR-020 |
| `EquivalenceClass` | FR-021, FR-022 |
| `ResolvedImage` | FR-023 a FR-025, FR-030 |
| `SpecSnapshot` | FR-026 a FR-029, FR-031 |
| `CheckpointEntry` / idempotência e atomicidade (§13) | FR-008, FR-009, FR-012, FR-026, FR-029 |
| Revalidação (ver contracts) | FR-032 |
| Export boundary (ver contracts) | FR-033 |
