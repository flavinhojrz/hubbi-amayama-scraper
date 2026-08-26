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

**Origem dos dados por nível de captura** (correção — research.md §16): `Model`/`Market` são constantes desta feature; `Spec Entry` (como candidato, antes de identidade confirmada) é descoberto via `DiscoveredSpecEntry` (§14, Nível A — market index); a enumeração de `Category`→`Group` esperados vem de `SpecGroupManifest` (§15, Nível B — spec navigation); o conteúdo de `Schema`→`Part` vem de `ParsedGroupDetail` (Nível C — group detail, ver `contracts/domain-contracts.md`), tipicamente um por `Group`.

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

Ver `contracts/input-contracts.md` §2 para o contrato completo. Resumo do tipo:

```
CaptureValidationResult:
  primary_outcome: ACCEPTED | CHALLENGE | TRANSLATION_CONTAMINATED | INVALID | INCOMPLETE
  evidence: dict   # todos os sinais detectados, não apenas o vencedor
```

`primary_outcome` é determinístico por construção — quando múltiplos sinais coexistem, a precedência **DEC-003** (`spec.md` §Decisions, contracts/input-contracts.md §2) decide: `CHALLENGE > TRANSLATION_CONTAMINATED > INVALID > INCOMPLETE > ACCEPTED`. `evidence` sempre preserva todos os sinais detectados, mesmo os que não determinaram `primary_outcome`. Somente `primary_outcome == ACCEPTED` segue para parsing.

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
| `collection_complete` | `bool` | sim | **Corrigido (research.md §17)**: `True` se e somente se (1) existe um `SpecGroupManifest` (§15) **autoritativo** para `(spec_key, run_id)`, e (2) todo `(category_slug, group_id)` presente nesse manifesto tem `CheckpointEntry` (§11) com status `ACCEPTED`, e (3) nenhum erro estrutural crítico invalida o manifesto. Sem manifesto autoritativo, `collection_complete` é sempre `False` — uma captura parcial de detalhe nunca define, sozinha, o universo esperado de grupos. |
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
| `raw_capture_id` | `str \| None` | não | Referência ao `RawCapture` (§4) associado a esta tentativa. **Corrigido (research.md §16)**: uma captura de `GROUP_DETAIL` corresponde tipicamente a **um único** `Group` (evidência de URL `.../<spec>/<category_slug>/<group_id>`) — a relação 1:1 é a suposição central. O campo permanece `str` (não uma lista) para não impedir, no futuro, que uma captura agregue mais de um grupo, mas isso deixou de ser a suposição de design. |
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
- `SpecSnapshot.collection_complete` (§6) só pode ser `True` quando existe manifesto autoritativo (§15) para a spec entry **e** todos os `(category_slug, group_id)` nele listados estão `ACCEPTED`.
- Raw já aceito permanece preservado independentemente do resultado de tentativas posteriores sobre o mesmo `Group` (Constitution §4).
- **Idempotência real** (ver §13 para o mecanismo completo — content-addressing por si só é insuficiente, apenas deduplica bytes físicos): a chave única `(run_id, spec_key, category_slug, group_id)` combinada com upsert transacional garante que repetir a mesma operação de checkpoint nunca produz uma segunda linha para a mesma unidade de progresso nem uma transição concorrente/repetida indevida para `ACCEPTED`.

**Leitura para replay (fecha o gap de resume após restart)**: além do upsert, o repositório de `CheckpointEntry` DEVE suportar `list_accepted(run_id, spec_key) -> list[CheckpointEntry]`, retornando todos os `CheckpointEntry` com `status == ACCEPTED` para aquela spec entry naquela run. Combinado com `raw_capture_id` de cada entrada e os ports `RawCaptureRepository`/`RawBlobStore` (contracts/ports-contract.md "Replay / Reconstrução determinística"), isso é suficiente para reconstruir o conteúdo bruto de todos os grupos já aceitos **exclusivamente a partir do que está persistido** — nenhum `ParsedGroupDetail` precisa sobreviver em memória entre processos. Exemplo: `Group A` e `Group B` `ACCEPTED` antes de o processo encerrar; uma nova instância consegue recuperar ambos via `list_accepted()` + `capture_repo.get()` + `blob_store.read()`, sem recoletar nada.

**Rastreabilidade**: FR-008, FR-009, FR-012, SC-004, User Story 7, research.md §9, §18.

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

### 13c. Reconstrução determinística + atomicidade da finalização (corrigido)

**Correção (revisão cirúrgica de TASKS, 2026-08-26)**: a formulação anterior recebia uma "árvore agregada" já pronta como parâmetro, sem nunca explicitar de onde ela viria após um restart do processo — nenhum `ParsedGroupDetail` sobrevive em memória entre processos por definição. `finalize_spec_entry()` não recebe mais uma árvore pronta: ela **reconstrói tudo a partir do que está persistido**, usando exclusivamente as leituras já definidas em §11 (`list_accepted`), §15 (`get_authoritative`) e `contracts/ports-contract.md` (`RawCaptureRepository.get()` + `RawBlobStore.read()`). Nenhum storage paralelo é introduzido.

A montagem da árvore, normalização e cálculo de fingerprints acontecem **antes** de qualquer escrita — nada é inserido como `SpecSnapshot` até que a árvore e os fingerprints existam por completo:

```
finalize_spec_entry(spec_key, run_id):

  # Fase 1 — reconstrução (leitura pura, fora de qualquer transação de escrita)
  1. manifest = manifest_repo.get_authoritative(spec_key, run_id)        # §15
     IF manifest is None: RETURN (sem manifesto autoritativo, nada a finalizar)

  2. accepted_entries = checkpoint_repo.list_accepted(run_id, spec_key)  # §11
     collection_complete = todo (category_slug, group_id) de manifest está
                            coberto por accepted_entries (ver §6)

  3. group_details = {}
     FOR cada CheckpointEntry em accepted_entries:
       raw_content = reconstruct_raw_content(entry.raw_capture_id,       # contracts/ports-contract.md
                                              capture_repo, blob_store)  # "Replay / Reconstrução determinística"
       group_details[(entry.category_slug, entry.group_id)] =
         parse_group_detail(raw_content, entry.category_slug, entry.group_id)
     # nenhum ParsedGroupDetail precisa ter sobrevivido em memória — todos são
     # recriados aqui, deterministicamente, a partir do raw persistido

  4. assembled_tree = assemble_spec_tree(manifest, group_details)        # contracts/domain-contracts.md
     normalized_tree = apply_normalization(assembled_tree)               # amayama-normalizer-v1
     fingerprint_set = compute_fingerprint_set(normalized_tree)          # amayama-fingerprint-v1

  5. accepted_checkpoint_fingerprint = multiset de (category_slug, group_id,
       raw_capture_id) sobre accepted_entries — §13b
     idempotency_key = SHA256("amayama:snapshot-idempotency:v1\0" +
                               canonical_json({run_id, spec_key, accepted_checkpoint_fingerprint}))
     state = VALID  se nenhum group_details[...] tem critical_error AND collection_complete == True
     state = INCOMPLETE  se collection_complete == False (sem critical_error nos grupos já ACCEPTED)

  # Fase 2 — transação única de metadados (única parte que toca o banco em modo escrita)
  BEGIN IMMEDIATE
    6. IF já existe SpecSnapshot com este idempotency_key:
         → retry idempotente — NÃO inserir novo snapshot; usar o existente nos passos 8-9
       ELSE:
         → INSERT novo SpecSnapshot (payload completo já calculado nos passos 4-5:
           fingerprint_set, state, idempotency_key — nunca um snapshot parcial)
         → persistir fingerprint_set associado (fingerprint_repo)
    7. IF o passo 6 inseriu um snapshot novo E já existia um SpecSnapshot anterior VALID/STALE
       para a mesma spec_identity:
         → UPDATE seu state para SUPERSEDED (nunca sobrescrito — FR-029)
    8. UPDATE current_spec_state para apontar ao snapshot_id do passo 6
       (o novo, ou o já existente em caso de retry idempotente) — last-known-good
    9. Marcar a finalização desta spec entry como concluída nesta run
  COMMIT
```

**Falha na Fase 1** (reconstrução/parsing/fingerprint) nunca chega a abrir a transação de escrita — não há nada para fazer rollback, e nenhum estado persistido é tocado; a finalização simplesmente pode ser tentada de novo mais tarde (idempotente por construção, já que a Fase 1 é pura leitura + computação determinística). **Falha na Fase 2** (transação SQLite) faz rollback completo: nenhum estado intermediário fica visível (nem snapshot duplicado, nem `current_spec_state` apontando para um snapshot inexistente, nem checkpoint "concluído" sem um snapshot consistente por trás). SQLite com escritor único (ou WAL com um único escritor por vez) é suficiente para este MVP — nenhum mecanismo de locking adicional é necessário; se acesso concorrente multi-processo se tornar um requisito futuro, ele é tratado na migração de `persistence/` (research.md §8), não neste desenho.

**Rastreabilidade**: FR-008, FR-009, FR-012, FR-026, FR-029, SC-004, SC-008.

---

## 14. `DiscoveredSpecEntry` (Nível A — market/spec index)

**Correção (research.md §16)**: fecha FR-001, que não tinha implementação explícita antes desta revisão.

| Campo | Tipo | Obrigatório | Notas |
|---|---|---|---|
| `market` | `str` | sim | Constante `"AMA-BR"` nesta feature. |
| `model_code` | `str` | sim | Não é único isoladamente (mesma regra de §1). |
| `amayama_catalog_id` | `str` | sim | Presente quando comprovado pela página de índice. |
| `production_period_raw` | `str \| None` | não | Texto verbatim; pode ser open-ended. |
| `production_start` | `date \| None` | não | Melhor esforço. |
| `production_end` | `date \| None` | não | `None` também representa produção em andamento. |
| `grade` | `str \| None` | não | Somente quando comprovado. |
| `configuration` | `str \| None` | não | Somente quando comprovado. |
| `source_url` | `str` | sim | URL da página de navegação da spec entry (Nível B). |
| `source_capture_id` | `str` | sim | `RawCapture.capture_id` da captura de `MARKET_INDEX` que originou esta entrada. |

**Invariantes**:
- `model_code` isolado nunca identifica uma entrada (mesma regra de FR-003).
- Campos opcionais ausentes na página de índice não são erro.
- `DiscoveredSpecEntry` é convertida em `SpecIdentity` (§1) completando `source`/`manufacturer`/`vehicle_model` (constantes desta feature) — a conversão não inventa nenhum campo não presente na descoberta.

**Rastreabilidade**: FR-001, FR-003, FR-004, FR-005.

---

## 15. `SpecGroupManifest` (Nível B — manifesto autoritativo de groups)

**Correção (research.md §17)**: fecha o gap de "quais são todos os `Group`s esperados" que deixava `collection_complete` (§6) subdefinido.

| Campo | Tipo | Obrigatório | Notas |
|---|---|---|---|
| `spec_key` | `str` | sim | `stable_key` (§1) da spec entry. |
| `source_capture_id` | `str` | sim | `RawCapture.capture_id` da captura de `SPEC_NAVIGATION` que originou o manifesto. |
| `discovered_at` | `datetime` | sim | |
| `categories` | `list[ManifestCategory]` | sim | Cada `ManifestCategory`: `{category_slug: str, groups: list[ManifestGroupRef]}`; cada `ManifestGroupRef`: `{group_id: str, source_url: str}` (URL da página de `GROUP_DETAIL`). |
| `manifest_complete` | `bool` | sim | `True` somente se a enumeração da página de navegação foi concluída sem truncamento/erro. |
| `validation_evidence` | `dict` | não | Evidência de auditoria da extração (ex.: contagem de categorias/grupos encontrados). |

**Autoridade do manifesto** — um `SpecGroupManifest` só é autoritativo para uma coleta `(spec_key, run_id)` quando **todas** as condições abaixo são verdadeiras:
1. a `RawCapture` de origem (`source_capture_id`) tem outcome `ACCEPTED` (contracts/input-contracts.md §2);
2. o parser de Nível B concluiu sem `critical_error` estrutural;
3. `manifest_complete == True`;
4. nenhum `(category_slug, group_id)` foi silenciosamente deduplicado — um par duplicado é `critical_error` (mesma invariante de §2, aplicada em tempo de parsing do manifesto).

**Invariantes**:
- `collection_complete` (§6) depende estritamente de existir um manifesto autoritativo — nunca é inferido a partir apenas dos `CheckpointEntry` já observados.
- Um manifesto não-autoritativo (qualquer condição acima falha) não pode ser usado para decidir completude — a spec entry permanece `collection_complete = False` até um manifesto autoritativo existir.

**Leitura para replay**: o repositório de `SpecGroupManifest` DEVE suportar `get_authoritative(spec_key, run_id) -> SpecGroupManifest | None`, aplicando as 4 condições de autoridade acima e retornando `None` quando alguma falha. É esse método — não uma referência em memória — que `finalize_spec_entry()` (contracts/snapshot-contract.md) consulta para obter o universo esperado de grupos, inclusive após um restart do processo.

**Rastreabilidade**: FR-001, FR-002, FR-012, FR-026.

---

## Resumo de rastreabilidade (entidade → FR)

| Entidade | FRs relacionados |
|---|---|
| `SpecIdentity` | FR-002 a FR-007, FR-021 |
| `DiscoveredSpecEntry` (§14) | FR-001, FR-003 a FR-005 |
| `SpecGroupManifest` (§15) | FR-001, FR-002, FR-012, FR-026 |
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
