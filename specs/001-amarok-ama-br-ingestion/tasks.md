# Tasks: MVP de Ingestão Amayama — Volkswagen Amarok (Mercado AMA BR)

**Feature**: `001-amarok-ama-br-ingestion` | **Branch**: `001-amarok-ama-br-ingestion`

**Input**: `spec.md` (aprovado, commit `eb7dd83`), `plan.md` (aprovado, commit `8328238`, corrigido nesta revisão), `research.md`, `data-model.md`, `quickstart.md`, `contracts/*.md` — todos em `specs/001-amarok-ama-br-ingestion/`.

**Revisão 2026-08-26 (a)**: a versão anterior de `tasks.md` recebeu `REQUEST_CHANGES` da coordenação SDD. Aquela revisão foi **renumerada integralmente** para incorporar 13 correções: (1) FR-001 materializado via parser de market index; (2) três níveis de parsing separados (market index / spec navigation / group detail); (3) `SpecGroupManifest` como fonte autoritativa do universo esperado de grupos; (4) correção da granularidade real de captura (uma `RawCapture` de detalhe = tipicamente um `Group`, não uma spec entry inteira); (5) *ports* `RawBlobStore`/`RawCaptureRepository` isolando Phase 3 da Phase 10; (6) teste explícito para `expected_identity_context`; (7) correção de `[P]` falso na Phase 1; (8) precedência de outcomes de validação **não resolvida por informed guess** — reportada como pendência ao PO; (9) `category_slug`/`group_id` resolvidos via padrão de URL evidenciado; (10) fixtures de regressão reformuladas para refletir granularidade real por `spec/category/group`; (11)(12) rastreabilidade e distribuição recalculadas do zero; (13) IDs contíguos sem duplicatas. Resultado daquela revisão: 261 tasks (T001–T261).

**Revisão 2026-08-26 (b)**: o PO aprovou **DEC-003** (precedência determinística de `primary_outcome` — `spec.md` §Decisions), fechando a única pendência da revisão anterior. A task antes bloqueada foi desbloqueada e decomposta em teste + implementação; todas as tasks a partir da antiga T069 foram deslocadas em +1 para abrir espaço (renumeração parcial, não integral — apenas o necessário para inserir a nova task sem reordenar o restante do documento). Resultado: 262 tasks (T001–T262).

**Revisão 2026-08-26 (c) — esta versão (correção cirúrgica)**: revisão direta identificou um blocker real de checkpoint/resume — `finalize_spec_entry()` recebia uma árvore agregada já pronta, sem nunca explicitar como ela seria reconstruída após um restart do processo (nenhum `ParsedGroupDetail` sobrevive em memória entre processos). Corrigido **sem renumerar nenhuma task**: `finalize_spec_entry(spec_key, run_id)` agora reconstrói tudo a partir do raw persistido (`manifest_repo.get_authoritative()` + `checkpoint_repo.list_accepted()` + `RawCaptureRepository.get()` + `RawBlobStore.read()` + `parse_group_detail()`), e a ordem foi corrigida para calcular a árvore/normalização/fingerprints **antes** de qualquer escrita de `SpecSnapshot` (T176, T184, T216 atualizadas; nenhum método novo foi necessário nos ports — `get()`/`read()` já definidos eram suficientes). O cenário de resume após restart foi incorporado a T251 (nenhuma task nova). Resultado: 262 tasks (T001–T262), IDs inalterados desta vez.

**Governança aplicada**: `.specify/memory/constitution.md`, `docs/sdd/EXECUTION_POLICY.md`, `AGENTS.md`, `CLAUDE.md`. Testes **não são opcionais** nesta feature (o template `tasks-template.md` diz "Tests are OPTIONAL"; essa instrução genérica é explicitamente ignorada, conforme `docs/sdd/EXECUTION_POLICY.md` §"Política de testes" e Constitution §12).

**Esta fase é exclusivamente de decomposição. Nenhuma task abaixo foi executada. `/speckit-implement` não foi disparado.**

## Convenções

- Formato: `- [ ] TXXX [P?] [USx?] Descrição — referências (FR/SC/DEC/contrato)`
- `[P]` **somente** quando a task edita um arquivo diferente de qualquer outra task incompleta/concorrente. Tasks que editam o mesmo arquivo compartilhado (ex. `pyproject.toml`) nunca são `[P]`, mesmo que configurem seções logicamente distintas.
- `[USx]` somente em tasks de fases ligadas a uma user story específica de `spec.md`. Fases de setup/foundation (1–2) e fases cross-cutting (10, 14, 15, 17) não carregam `[USx]` como regra — exceto quando uma sub-task de uma fase cross-cutting pertence claramente a uma entidade de uma única story (ex. uma migration específica), caso em que a tag é aplicada à task individual, não à fase inteira.
- Caminhos de arquivo são os alvos que a implementação futura deve criar — **nenhum deles existe ainda**.
- Mapeamento de fases → user stories (spec.md): US1=descoberta/identidade, US2=raw auditável + human-in-the-loop, US3=normalização/fingerprints, US4=equivalência/dedup, US5=fallback de imagem, US6=snapshots/revalidação, US7=checkpoint/resume.

---

## Phase 1 — Project Setup

**Propósito**: preparar a estrutura técnica aprovada em `research.md` §1–§6. Nenhuma lógica de domínio é implementada nesta fase.

**Nota de correção**: a versão anterior marcava várias tasks de configuração de `pyproject.toml` como `[P]`, violando a própria convenção (mesmo arquivo compartilhado). Corrigido abaixo: a cadeia de `pyproject.toml` é sequencial; apenas tasks que tocam arquivos genuinamente distintos permanecem `[P]`.

- [ ] T001 Criar `pyproject.toml` (PEP 621) na raiz do repositório com metadados do projeto (`name = "amayama-scraper"`) — research.md §2
- [ ] T002 Configurar `hatchling` como build backend em `pyproject.toml` — research.md §2 (depende de T001, mesmo arquivo)
- [ ] T003 Declarar `requires-python = ">=3.11"` em `pyproject.toml` — research.md §1 (depende de T002, mesmo arquivo)
- [ ] T004 Adicionar dependências de runtime `beautifulsoup4` e `lxml` em `pyproject.toml` — research.md §4 (depende de T003, mesmo arquivo)
- [ ] T005 Adicionar dependências de desenvolvimento `pytest`, `pytest-cov`, `ruff`, `mypy` em `pyproject.toml` (grupo `dev`) — research.md §5/§6 (depende de T004, mesmo arquivo)
- [ ] T006 Configurar `pytest` (testpaths, markers) em `pyproject.toml` — research.md §5 (depende de T005, mesmo arquivo)
- [ ] T007 Configurar `pytest-cov` (relatório de cobertura) em `pyproject.toml` — research.md §5 (depende de T006, mesmo arquivo)
- [ ] T008 Configurar `ruff` (lint + format) em `pyproject.toml` — research.md §6 (depende de T007, mesmo arquivo)
- [ ] T009 [P] Configurar `mypy --strict` em `mypy.ini` (arquivo próprio — genuinamente paralelo à cadeia de `pyproject.toml`) — research.md §3/§6
- [ ] T010 [P] Criar `src/amayama_scraper/__init__.py` — plan.md "Project Structure"
- [ ] T011 [P] Criar scaffolding de subpacotes vazios: `src/amayama_scraper/{ingestion,validation,parsing,domain,normalization,fingerprints,equivalence,assets,snapshots,persistence,checkpoint,orchestration,export}/__init__.py` — plan.md "Project Structure"
- [ ] T012 [P] Criar scaffolding de testes: `tests/{unit,parser,regression,integration}/__init__.py` e diretório `tests/fixtures/` (sem `__init__.py`, apenas dados) — plan.md "Project Structure"

**Checkpoint**: estrutura de projeto pronta; nenhum código de domínio criado ainda.

---

## Phase 2 — Domain Foundations

**Propósito**: dataclasses e invariantes estruturais puras (sem I/O, sem persistência) para todas as entidades de `data-model.md`, incluindo as duas entidades novas desta revisão (`DiscoveredSpecEntry`, `SpecGroupManifest`) e os *ports* de persistência (`contracts/ports-contract.md`) que mantêm a Phase 3 independente da Phase 10.

- [ ] T013 [P] Test: invariantes estruturais de `SpecIdentity` — tupla normativa de 6 campos, `stable_key` determinístico (hash), `display_key` com escaping, `production_start`/`production_end`/`source_url` excluídos do `stable_key` em `tests/unit/test_spec_identity.py` — FR-002 a FR-005, FR-021; data-model.md §1; research.md §10
- [ ] T014 Implementar `SpecIdentity` (dataclass `frozen, slots`) + `stable_key()` + `display_key()` em `src/amayama_scraper/domain/identity.py` — mesmas referências (depende de T013)
- [ ] T015 [P] Test: `DiscoveredSpecEntry` — campos preservados quando presentes, `model_code` isolado não é identificador, conversão para `SpecIdentity` não inventa campo ausente em `tests/unit/test_discovered_spec_entry.py` — FR-001, FR-003 a FR-005; data-model.md §14
- [ ] T016 Implementar `DiscoveredSpecEntry` (dataclass) + `to_spec_identity()` em `src/amayama_scraper/domain/discovery.py` — mesmas referências (depende de T014, T015)
- [ ] T017 [P] Test: invariantes de `Category`/`Group`/`Schema` — `group_id` preservado como string com zeros à esquerda, `Group` vazio é válido em `tests/unit/test_hierarchy.py` — data-model.md §2 (nota: a invariante de `group_id` duplicado passou a ser verificada no manifesto — Nível B, T027 — não aqui)
- [ ] T018 Implementar `Category`, `Group`, `Schema` em `src/amayama_scraper/domain/hierarchy.py` — mesma referência (depende de T017)
- [ ] T019 [P] Test: `SpecGroupManifest` — condições de autoridade (RawCapture ACCEPTED, sem critical_error, `manifest_complete=True`, sem `(category_slug, group_id)` duplicado), `manifest_complete=False` quando truncado em `tests/unit/test_spec_group_manifest.py` — data-model.md §15; research.md §17
- [ ] T020 Implementar `SpecGroupManifest` + `ManifestCategory` + `ManifestGroupRef` (dataclasses) + `is_manifest_authoritative()` em `src/amayama_scraper/domain/manifest.py` — mesmas referências (depende de T018, T019)
- [ ] T021 [P] Test: invariantes de `Part` — campos opcionais ausentes não invalidam a peça, `pr_codes` default lista vazia em `tests/unit/test_part.py` — FR-013, FR-014; data-model.md §3
- [ ] T022 Implementar `Part` (dataclass) em `src/amayama_scraper/domain/part.py` — mesmas referências (depende de T021)
- [ ] T023 [P] Test: `OemReference` como projeção derivada de `oem_code` distintos de um `Schema` (nunca fonte de dado própria) em `tests/unit/test_oem_reference.py` — research.md §11
- [ ] T024 Implementar `OemReference` (dataclass + função de derivação) em `src/amayama_scraper/domain/oem_reference.py` — mesmas referências (depende de T023)
- [ ] T025 [P] Test: imutabilidade de `RawBlob` e campos (`content_hash` chave, `size_bytes`, `storage_path`, `first_seen_at`) em `tests/unit/test_raw_blob.py` — data-model.md §4a
- [ ] T026 Implementar `RawBlob` (dataclass `frozen`) em `src/amayama_scraper/ingestion/raw_blob.py` — mesmas referências (depende de T025)
- [ ] T027 [P] Test: `RawCapture` imutável, `capture_id` sempre distinto mesmo com `content_hash` igual, campo `capture_kind` presente em `tests/unit/test_raw_capture.py` — data-model.md §4b; research.md §16
- [ ] T028 Implementar `RawCapture` (dataclass `frozen`, com `capture_kind: MARKET_INDEX|SPEC_NAVIGATION|GROUP_DETAIL`) em `src/amayama_scraper/ingestion/raw_capture.py` — mesmas referências (depende de T027)
- [ ] T029 [P] Definir *ports* `RawBlobStore`/`RawCaptureRepository` (`typing.Protocol`, sem SQLite/filesystem concreto) em `src/amayama_scraper/ingestion/ports.py` — contracts/ports-contract.md; research.md §18 (depende de T026, T028)
- [ ] T030 [P] Test: implementações *fake* em memória dos ports — `get_or_create` idempotente (mesmo `content_hash` não duplica), `save` sempre insere nova observação, e **round-trip de leitura**: `get(capture_id)` devolve a `RawCapture` salva e `read(content_hash)` devolve os bytes originais — o par escrita+leitura é o que viabiliza replay (contracts/ports-contract.md "Replay / Reconstrução determinística") em `tests/unit/test_ports_fakes.py` — contracts/ports-contract.md
- [ ] T031 Implementar `InMemoryRawBlobStore`/`InMemoryRawCaptureRepository` (fakes de teste, satisfazendo os ports de T029, incluindo `get()`/`read()`) em `tests/unit/fakes.py` — mesma referência (depende de T029, T030)
- [ ] T032 [P] Test: campos estruturais de `CollectionRun` (`run_id`, `scope`, timestamps) em `tests/unit/test_collection_run.py` — data-model.md §11
- [ ] T033 Implementar `CollectionRun` (dataclass) em `src/amayama_scraper/checkpoint/collection_run.py` — mesmas referências (depende de T032)
- [ ] T034 [P] Test: enum de status de `CheckpointEntry` (`PENDING/IN_PROGRESS/ACCEPTED/REJECTED`) e regra pura de transição (nunca sai de `ACCEPTED`) em `tests/unit/test_checkpoint_entry.py` — data-model.md §11
- [ ] T035 Implementar `CheckpointEntry` (dataclass) + função pura `transition()` em `src/amayama_scraper/checkpoint/checkpoint_entry.py` — mesmas referências (depende de T034)
- [ ] T036 [P] Test: campos de `SpecSnapshot` + enum de 5 estados (`VALID/INCOMPLETE/STALE/SUPERSEDED/INVALID`) + campo `idempotency_key` + imutabilidade em `tests/unit/test_snapshot_entity.py` — FR-027; data-model.md §6, §13b
- [ ] T037 Implementar `SpecSnapshot` (dataclass `frozen`) + enum de estado em `src/amayama_scraper/snapshots/snapshot.py` — mesmas referências (depende de T036)
- [ ] T038 [P] Test: `FingerprintSet` — 4 hashes independentes + `fingerprint_version` em `tests/unit/test_fingerprint_set.py` — data-model.md §7
- [ ] T039 Implementar `FingerprintSet` (dataclass) em `src/amayama_scraper/fingerprints/types.py` — mesmas referências (depende de T038)
- [ ] T040 [P] Test: `EquivalenceResult` — enums `parts_relation`/`schema_relation`/`image_relation`/`comparison_valid` em `tests/unit/test_equivalence_result.py` — data-model.md §8
- [ ] T041 Implementar `EquivalenceResult` + enums em `src/amayama_scraper/equivalence/types.py` — mesmas referências (depende de T040)
- [ ] T042 [P] Test: `EquivalenceClass`/`ClusterAssignment` — `cluster_key`, `representative_spec_ref`, `member_spec_refs` em `tests/unit/test_equivalence_class.py` — data-model.md §9
- [ ] T043 Implementar `EquivalenceClass` + `ClusterAssignment` (dataclasses) em `src/amayama_scraper/equivalence/cluster_types.py` — mesmas referências (depende de T042)
- [ ] T044 [P] Test: `ResolvedImage` — `origin_spec_ref` obrigatório, `resolved_within_cluster_key` obrigatório quando `is_fallback=True` em `tests/unit/test_resolved_image.py` — data-model.md §10
- [ ] T045 Implementar `ResolvedImage` (dataclass) em `src/amayama_scraper/assets/types.py` — mesmas referências (depende de T044)
- [ ] T046 [P] Test: campos de `CurrentSpecState` (projeção, não fonte de verdade) em `tests/unit/test_current_spec_state.py` — data-model.md §12
- [ ] T047 Implementar `CurrentSpecState` (dataclass) em `src/amayama_scraper/domain/current_state.py` — mesmas referências (depende de T046)
- [ ] T048 [P] Test de fronteira arquitetural: `domain/`, `normalization/`, `fingerprints/`, `equivalence/`, `assets/`, `snapshots/` não importam nada de transporte/browser/SQLite; `SpecIdentity` não possui campos `body`/`engine`/`drivetrain`/`transmission` em `tests/unit/test_architecture_boundaries.py` — FR-006, FR-034; research.md §18

**Checkpoint**: todas as entidades de `data-model.md` (incluindo `DiscoveredSpecEntry` e `SpecGroupManifest`) existem como dataclasses puras e testadas estruturalmente; os *ports* de persistência existem e têm fakes testados. Nenhuma persistência concreta, parsing ou I/O real ainda.

---

## Phase 3 — Raw Ingestion Contracts and Validation [US2]

**Propósito**: materializar `contracts/input-contracts.md` — entrada agnóstica de transporte (agora com `capture_kind`), provenance, e os 5 outcomes de validação. **Corrigido**: `accept_capture()` usa os *ports* da Phase 2 (T029/T031) por injeção de dependência — nenhuma dependência oculta da Phase 10; totalmente testável offline com os fakes.

- [ ] T049 [P] [US2] Test: contrato `RawCaptureInput` — `source_url` deve ser absoluta, `raw_content` vazio é rejeitado como `INVALID`, `capture_kind` deve ser um dos 3 valores válidos em `tests/unit/test_raw_capture_input.py` — contracts/input-contracts.md §1
- [ ] T050 [US2] Implementar `RawCaptureInput` (dataclass, com `capture_kind`) + validação de pré-condições em `src/amayama_scraper/ingestion/capture_input.py` — mesma referência (depende de T049)
- [ ] T051 [P] [US2] Test: `content_hash()` determinístico (SHA-256 de `raw_content`) em `tests/unit/test_content_hash.py` — data-model.md §4a
- [ ] T052 [US2] Implementar `content_hash()` em `src/amayama_scraper/ingestion/hashing.py` — mesma referência (depende de T051)
- [ ] T053 [P] [US2] Test: `accept_capture(input, blob_store, capture_repo)` grava `RawBlob` (dedup por `content_hash`, via `blob_store.get_or_create()`) e nova `RawCapture` (via `capture_repo.save()`) ANTES de qualquer validação de conteúdo — usando os fakes de T031, sem SQLite — em `tests/unit/test_accept_capture.py` — FR-008, FR-009; contracts/input-contracts.md §1 pós-condição; contracts/ports-contract.md
- [ ] T054 [US2] Implementar `accept_capture()` recebendo `RawBlobStore`/`RawCaptureRepository` por parâmetro (dependency injection, nenhum import de SQLite) em `src/amayama_scraper/ingestion/accept.py` — mesmas referências (depende de T026, T028, T029, T031, T052, T053)
- [ ] T055 [P] [US2] Test: duas `RawCaptureInput` com `raw_content` byte-idêntico produzem um único `RawBlob` (via o mesmo `blob_store` fake) e duas `RawCapture` distintas (nunca colapsadas) em `tests/unit/test_raw_observation_distinctness.py` — data-model.md §4b (depende de T054)
- [ ] T056 [P] [US2] Test: `CaptureValidationResult` — enum de outcome exaustivo e mutuamente exclusivo em `tests/unit/test_capture_validation_result.py` — contracts/input-contracts.md §2
- [ ] T057 [US2] Implementar `CaptureValidationResult` (dataclass) em `src/amayama_scraper/validation/types.py` — mesma referência (depende de T056)
- [ ] T058 [P] [US2] Test + fixture: detector `CHALLENGE` (CAPTCHA/Cloudflare/"Just a moment") usando `tests/fixtures/challenge_cloudflare.html` em `tests/parser/test_challenge_detection.py` — Constitution §5, FR-010
- [ ] T059 [US2] Implementar detector de challenge em `src/amayama_scraper/validation/detectors/challenge.py` — mesmas referências (depende de T058)
- [ ] T060 [P] [US2] Test + fixture: detector `TRANSLATION_CONTAMINATED` usando `tests/fixtures/translation_contaminated.html` em `tests/parser/test_translation_detection.py` — FR-010
- [ ] T061 [US2] Implementar detector de tradução contaminada em `src/amayama_scraper/validation/detectors/translation.py` — mesmas referências (depende de T060)
- [ ] T062 [P] [US2] Test + fixture: detector `INVALID` — estrutura mínima esperada **parametrizada por `capture_kind`** (Nível A/B/C têm estruturas mínimas distintas — contracts/domain-contracts.md) usando `tests/fixtures/invalid_structure.html` em `tests/parser/test_invalid_structure_detection.py` — FR-010
- [ ] T063 [US2] Implementar detector de HTML/estrutura inválida, parametrizado por `capture_kind`, em `src/amayama_scraper/validation/detectors/structure.py` — mesmas referências (depende de T062)
- [ ] T064 [P] [US2] Test + fixture: classificação `INCOMPLETE` (estruturalmente válido, captura parcial) usando `tests/fixtures/incomplete_capture.html` em `tests/parser/test_incomplete_detection.py` — FR-010
- [ ] T065 [US2] Implementar detector de captura incompleta em `src/amayama_scraper/validation/detectors/incomplete.py` — mesmas referências (depende de T064)
- [ ] T066 [P] [US2] Test: `classify_capture()` retorna exatamente um dos 5 outcomes **para os casos de sinal único** (challenge OU tradução OU inválido OU incompleto OU aceito — nunca dois simultâneos) em `tests/unit/test_classify_capture_single_signal.py` — contracts/input-contracts.md §2
- [ ] T067 [US2] Implementar `classify_capture()` para os casos de sinal único (cada detector é consultado; se exatamente um sinaliza rejeição, esse é o outcome; se nenhum sinaliza, `ACCEPTED`) em `src/amayama_scraper/validation/classify.py` — mesmas referências (depende de T059, T061, T063, T065, T066)
- [ ] T068 [P] [US2] Test: precedência determinística de `primary_outcome` (DEC-003) quando múltiplos sinais coexistem — `challenge+invalid → CHALLENGE`; `tradução+invalid → TRANSLATION_CONTAMINATED`; `invalid+incomplete → INVALID`; e `evidence` preserva **todos** os sinais detectados em cada caso, mesmo os que não determinaram `primary_outcome` — em `tests/unit/test_classify_capture_precedence.py` — DEC-003; contracts/input-contracts.md §2 (depende de T067)
- [ ] T069 [US2] Implementar a precedência determinística `CHALLENGE > TRANSLATION_CONTAMINATED > INVALID > INCOMPLETE > ACCEPTED` em `classify_capture()` — `primary_outcome` segue a ordem de DEC-003; `evidence` continua agregando todos os sinais dos detectores (T059, T061, T063, T065), nunca apenas o vencedor — em `src/amayama_scraper/validation/classify.py` — mesmas referências (depende de T067, T068)
- [ ] T070 [P] [US2] Test: outcome `CHALLENGE` gera sinal/estado de human-in-the-loop, nunca é tratado como página vazia válida em `tests/unit/test_challenge_routing.py` — FR-011
- [ ] T071 [US2] Implementar roteamento human-in-the-loop em `src/amayama_scraper/validation/human_in_the_loop.py` — mesma referência (depende de T070)
- [ ] T072 [P] [US2] Test de salvaguarda: `validation/` não contém termos/lógica de bypass (ex.: "solver", "bypass", "undetected-chromedriver") — falha se detectado em `tests/unit/test_no_bypass_forbidden_terms.py` — Constitution §5, AGENTS.md

**Checkpoint (US2 completa)**: raw é preservado de forma imutável e auditável (via ports, sem dependência oculta de persistência concreta) antes de qualquer transformação; captura é classificada corretamente, incluindo a precedência determinística DEC-003 para sinais simultâneos; challenge nunca é tratado como conteúdo válido; nenhum bypass existe.

---

## Phase 4 — Amayama Parsing: Três Níveis [US1]

**Propósito**: materializar `contracts/domain-contracts.md` — três parsers separados (Nível A/B/C), a resolução de `category_slug`/`group_id` via URL, e a montagem da árvore agregada. **Corrigido**: FR-001 agora tem implementação (Nível A); o antigo `parse_spec_entry()` único foi decomposto; `group_id` duplicado é verificado no manifesto (Nível B), não mais no detalhe (Nível C).

### Nível A — Market Index (implementa FR-001)

- [ ] T073 [US1] **Investigação técnica localizada** (NÃO é autorização para browser automation): verificar a estrutura real da página de índice do mercado `AMA-BR` contra fixture de HTML já capturada manualmente (browser-in-the-loop, DEC-001); documentar o seletor/estratégia de extração confirmado em `contracts/domain-contracts.md` "Nível A"; se a evidência for insuficiente para algum campo (`market`/`model_code`/`amayama_catalog_id`/período/`source_url`/`grade`/`configuração`), registrar exatamente o que falta, sem inventar — research.md "Nível A"
- [ ] T074 [P] [US1] Test + fixtures: `parse_market_spec_index()` cobrindo múltiplos spec entries, mesmo `model_code` com `amayama_catalog_id` distintos, período open-ended, campo opcional ausente, estrutura inesperada (drift) — fixtures em `tests/fixtures/market_index/{valid_multi_entry,same_model_code_diff_catalog,open_ended_period,missing_optional_field,structural_drift}.html` + `tests/parser/test_market_index_parsing.py` — FR-001; contracts/domain-contracts.md "Nível A" (depende de T073)
- [ ] T075 [US1] Implementar `parse_market_spec_index()` em `src/amayama_scraper/parsing/market_index.py` — mesmas referências (depende de T016, T074)

### Nível B — Spec Group Manifest (fecha o gap de universo esperado de grupos)

- [ ] T076 [US1] **Investigação técnica localizada** (NÃO é autorização para browser automation): verificar a estrutura real da página de navegação de uma spec entry contra fixture já capturada; documentar o seletor/estratégia de extração de `categories`/`groups` esperados em `contracts/domain-contracts.md` "Nível B"; registrar qualquer gap sem inventar — research.md "Nível B"
- [ ] T077 [P] [US1] Test + fixtures: `parse_spec_group_manifest()` — manifesto com múltiplas categorias/grupos, `(category_slug, group_id)` duplicado (`critical_error`, manifesto não-autoritativo), manifesto truncado (`manifest_complete=False`), estrutura inesperada — fixtures em `tests/fixtures/spec_navigation/{valid_manifest,duplicate_group_id,truncated_manifest,structural_drift}.html` + `tests/parser/test_spec_group_manifest_parsing.py` — data-model.md §15; research.md §17 (depende de T076)
- [ ] T078 [US1] Implementar `parse_spec_group_manifest()` — inclui detecção de `(category_slug, group_id)` duplicado como `critical_error` — em `src/amayama_scraper/parsing/spec_group_manifest.py` — mesmas referências (depende de T020, T077)

### Nível C — Group Detail (seletores v1 já evidenciados)

- [ ] T079 [P] [US1] Test: constantes de seletores v1 correspondem exatamente às documentadas em `tests/unit/test_selectors_v1.py` — contracts/domain-contracts.md "Nível C"
- [ ] T080 [US1] Definir constantes de seletores v1 (`.epcVariation__details`, `.epcSchema__schemas`, `.epcSchema__schema[data-id]`, `.img__description`, `.imgMap img[src]`, `.entriesTable`, `tr[data-key]`, `.entriesPncTable__groupHeader`, `.entriesTable__number`, `.entriesTable__description`, `.entriesPncDescriptionTable`, `.entriesTable__period`, `.entriesTable__required`) em `src/amayama_scraper/parsing/selectors.py` — mesma referência (depende de T079)
- [ ] T081 [P] [US1] Test: `extract_category_and_group_from_url()` — verificação contra URL de evidência (`.../s1bc3x-56087/front-axle-steering/407` → `("front-axle-steering", "407")`) e fixtures adicionais já capturadas; falha explícita (drift) quando a URL não tem o formato de 2 segmentos finais esperado; nunca infere de texto traduzido em `tests/unit/test_extract_category_group_from_url.py` — research.md §19; contracts/domain-contracts.md "Nível C"
- [ ] T082 [US1] Implementar `extract_category_and_group_from_url()` em `src/amayama_scraper/parsing/url_extraction.py` — mesmas referências (depende de T081)
- [ ] T083 [P] [US1] Test: dataclasses `ParsedGroupDetail`/`ParsedSchema`/`ParsedPart` e semântica de `field_status` (`PRESENT`/`ABSENT`/`PARSE_ERROR`) em `tests/unit/test_parse_result_types.py` — contracts/domain-contracts.md "Nível C"
- [ ] T084 [US1] Implementar dataclasses de resultado de parsing de detalhe em `src/amayama_scraper/parsing/results.py` — mesma referência (depende de T083)
- [ ] T085 [P] [US1] Test + fixture: HTML válido de um group detail completo (múltiplos schemas/parts de UM group) em `tests/fixtures/group_detail/valid_group_detail.html` + `tests/parser/test_parse_group_detail_valid.py` — quickstart.md
- [ ] T086 [US1] Implementar `parse_group_detail(html, category_slug, group_id)` — caminho feliz — em `src/amayama_scraper/parsing/group_detail.py` — mesmas referências (depende de T080, T082, T084, T085)
- [ ] T087 [P] [US1] Test + fixture: campos opcionais ausentes (`oem_code`, `description`, `details`, `period`, `pr_codes`, `quantity`, `image_url`) em `tests/fixtures/group_detail/missing_optional_fields.html` + `tests/parser/test_parse_missing_optional.py` — FR-014
- [ ] T088 [US1] Implementar tratamento de `field_status=ABSENT` por campo opcional em `src/amayama_scraper/parsing/group_detail.py` — mesmas referências (depende de T086, T087)
- [ ] T089 [P] [US1] Test + fixture: `Group` vazio (sem `Schema`/`Part` na sua própria página de detalhe) em `tests/fixtures/group_detail/empty_group.html` + `tests/parser/test_parse_empty_group.py` — data-model.md §2
- [ ] T090 [US1] Implementar suporte a grupo vazio em `parse_group_detail()` — mesmas referências (depende de T086, T089)
- [ ] T091 [P] [US1] Test + fixture: drift estrutural (seletor esperado ausente/estrutura incompatível) em `tests/fixtures/group_detail/structural_drift.html` + `tests/parser/test_parse_structural_drift.py` — ponto 20 do PLAN, FR-010
- [ ] T092 [US1] Implementar falha explícita de drift estrutural — nunca parsing permissivo silencioso — em `src/amayama_scraper/parsing/group_detail.py` — mesmas referências (depende de T086, T091)
- [ ] T093 [P] [US1] Test de integração: capturas `CHALLENGE`/`TRANSLATION_CONTAMINATED`/`INVALID`/`INCOMPLETE` (fixtures da Phase 3) nunca invocam nenhum dos três parsers (Nível A/B/C) em `tests/integration/test_parser_never_reached_on_rejected_capture.py` — contracts/input-contracts.md invariante "somente ACCEPTED segue para parsing" (depende de T067, T075, T078, T086)
- [ ] T094 [P] [US1] Test: `expected_identity_context` — contexto esperado compatível → sucesso; `model_code` divergente → sinalizado; `amayama_catalog_id` divergente → sinalizado; `market` divergente → sinalizado; ausência de contexto esperado → nenhum erro inventado em `tests/unit/test_identity_context_divergence.py` — data-model.md §4b
- [ ] T095 [US1] Implementar detecção de divergência entre `expected_identity_context` e identidade efetivamente parseada em `src/amayama_scraper/parsing/identity_context.py` — mesma referência (depende de T094)
- [ ] T096 [P] [US1] Test: `parser_version` (`amayama-parser-v1`) versionado e anexado ao resultado de cada um dos três níveis de parsing em `tests/unit/test_parser_version.py` — Constitution §13
- [ ] T097 [US1] Anexar `parser_version` aos resultados de `parse_market_spec_index()`, `parse_spec_group_manifest()` e `parse_group_detail()` — mesma referência (depende de T075, T078, T086, T096)

### Montagem da árvore agregada

- [ ] T098 [P] [US1] Test: `assemble_spec_tree(manifest, group_details)` — manifesto completo + todos os grupos `ACCEPTED` produz árvore completa; manifesto com grupos faltando produz árvore parcial (marcada incompleta); manifesto não-autoritativo produz `None`/erro em `tests/unit/test_assemble_spec_tree.py` — contracts/domain-contracts.md "Montagem da árvore agregada"
- [ ] T099 [US1] Implementar `assemble_spec_tree()` em `src/amayama_scraper/parsing/assembly.py` — mesma referência (depende de T018, T020, T084, T098)

**Checkpoint (US1 completa, com Phase 2/3)**: FR-001 implementado (Nível A); manifesto autoritativo (Nível B) define o universo esperado de grupos; detalhe (Nível C) produz peças por grupo, falhando explicitamente diante de estrutura inesperada; a árvore agregada é montada de forma auditável a partir do manifesto + grupos aceitos.

---

## Phase 5 — Normalization v1 [US3]

**Propósito**: materializar `amayama-normalizer-v1` (contracts/normalization-fingerprint-contracts.md). Inalterada em relação à revisão anterior — nenhuma correção pedida aqui.

- [ ] T100 [P] [US3] Test: normalização de texto genérico — NFKC, NBSP/newline/whitespace, trim em `tests/unit/test_normalize_text.py` — Constitution §7
- [ ] T101 [US3] Implementar `normalize_text()` em `src/amayama_scraper/normalization/text.py` — mesma referência (depende de T100)
- [ ] T102 [P] [US3] Test: normalização de OEM — `strip`+`upper`+remoção de whitespace técnico interno quando comprovadamente formatação em `tests/unit/test_normalize_oem.py` — contracts/normalization-fingerprint-contracts.md
- [ ] T103 [US3] Implementar `normalize_oem()` em `src/amayama_scraper/normalization/oem.py` — mesma referência (depende de T102)
- [ ] T104 [P] [US3] Test: `schema_id` trim + `pnc` trim+upper em `tests/unit/test_normalize_identifiers.py` — contracts/normalization-fingerprint-contracts.md
- [ ] T105 [US3] Implementar `normalize_schema_id()`/`normalize_pnc()` em `src/amayama_scraper/normalization/identifiers.py` — mesma referência (depende de T104)
- [ ] T106 [P] [US3] Test: `pr_codes` — `strip`+`upper`+ordenação lexicográfica quando lista estruturada em `tests/unit/test_normalize_pr_codes.py` — contracts/normalization-fingerprint-contracts.md
- [ ] T107 [US3] Implementar `normalize_pr_codes()` em `src/amayama_scraper/normalization/pr_codes.py` — mesma referência (depende de T106)
- [ ] T108 [P] [US3] Test de regressão negativa: pontuação preservada, nenhuma remoção arbitrária em `tests/unit/test_normalize_preserves_punctuation.py` — Constitution §7
- [ ] T109 [P] [US3] Test de regressão negativa: normalização NÃO aplica tradução/stemming/fuzzy matching/sinonímia/correção ortográfica/remoção arbitrária de acentos em `tests/unit/test_normalize_forbidden_transforms.py` — FR-016
- [ ] T110 [US3] Definir constante `normalizer_version = "amayama-normalizer-v1"` + função agregadora `apply_normalization()` em `src/amayama_scraper/normalization/version.py` — Constitution §13 (depende de T101, T103, T105, T107)
- [ ] T111 [P] [US3] Test: `normalizer_version` determinístico e anexado ao resultado normalizado em `tests/unit/test_normalizer_version.py` — mesma referência (depende de T110)

**Checkpoint (US3 parcial — normalização)**: normalização determinística, conservadora e versionada, sem qualquer transformação semântica proibida.

---

## Phase 6 — Canonical Serialization and Fingerprints v1 [US3]

**Propósito**: materializar `amayama-fingerprint-v1` (contracts/normalization-fingerprint-contracts.md). Inalterada — opera sobre a árvore agregada (`assemble_spec_tree()`, Phase 4), não sobre o antigo `ParsedSpecEntry`.

- [ ] T112 [P] [US3] Test: serialização JSON canônica determinística (`sort_keys`, `ensure_ascii`, `separators` compactos) em `tests/unit/test_canonical_json.py` — research.md §7
- [ ] T113 [US3] Implementar `canonical_json()` em `src/amayama_scraper/fingerprints/canonical.py` — mesma referência (depende de T112)
- [ ] T114 [P] [US3] Test: `part_fingerprint` — determinismo, domain separator (`amayama:part:v1\0`), campos canônicos exatos (`schema_id, pnc, oem, description, details, period, required`) e **`pr_codes` explicitamente EXCLUÍDO** em `tests/unit/test_part_fingerprint.py` — FR-017; contracts/normalization-fingerprint-contracts.md
- [ ] T115 [US3] Implementar `part_fingerprint()` em `src/amayama_scraper/fingerprints/part.py` — mesmas referências (depende de T113, T114)
- [ ] T116 [P] [US3] Test: `group_fingerprint` — multiset (ordem irrelevante, duplicatas alteram resultado), grupo vazio produz hash válido em `tests/unit/test_group_fingerprint.py` — Constitution §8
- [ ] T117 [US3] Implementar `group_fingerprint()` em `src/amayama_scraper/fingerprints/group.py` — mesmas referências (depende de T115, T116)
- [ ] T118 [P] [US3] Test: `category_fingerprint` — multiset inclui grupos vazios, `category_slug` participa em `tests/unit/test_category_fingerprint.py` — Constitution §8
- [ ] T119 [US3] Implementar `category_fingerprint()` em `src/amayama_scraper/fingerprints/category.py` — mesmas referências (depende de T117, T118)
- [ ] T120 [P] [US3] Test: `spec_parts_hash` — multiset de `category_fingerprint`; identidade da spec NUNCA entra no hash em `tests/unit/test_spec_parts_hash.py` — Constitution §8
- [ ] T121 [US3] Implementar `spec_parts_hash()` sobre `AssembledSpecTree` (Phase 4) em `src/amayama_scraper/fingerprints/spec.py` — mesmas referências (depende de T099, T119, T120)
- [ ] T122 [P] [US3] Test: `structure_hash` — multiset de categories/groups/schemas, sem conteúdo de parts em `tests/unit/test_structure_hash.py` — data-model.md §7
- [ ] T123 [US3] Implementar `structure_hash()` em `src/amayama_scraper/fingerprints/structure.py` — mesmas referências (depende de T122)
- [ ] T124 [P] [US3] Test: `schema_semantic_hash` — multiset de `schema_id`, independente de `spec_parts_hash` em `tests/unit/test_schema_semantic_hash.py` — data-model.md §7
- [ ] T125 [US3] Implementar `schema_semantic_hash()` em `src/amayama_scraper/fingerprints/schema_semantic.py` — mesmas referências (depende de T124)
- [ ] T126 [P] [US3] Test: `image_hash` — multiset de imagens próprias, independente de `spec_parts_hash` em `tests/unit/test_image_hash.py` — FR-018
- [ ] T127 [US3] Implementar `image_hash()` em `src/amayama_scraper/fingerprints/image.py` — mesmas referências (depende de T126)
- [ ] T128 [P] [US3] Test: mudança só de imagem NÃO altera `spec_parts_hash` em `tests/unit/test_image_change_does_not_affect_parts_hash.py` — FR-030, SC-009 (depende de T121, T127)
- [ ] T129 [P] [US3] Test: `group_id` com zeros à esquerda é preservado no fingerprint (nunca convertido para `int`) em `tests/unit/test_fingerprint_preserves_leading_zeros.py` — data-model.md §2 (depende de T117)
- [ ] T130 [US3] Definir constante `fingerprint_version = "amayama-fingerprint-v1"` + `compute_fingerprint_set()` agregador em `src/amayama_scraper/fingerprints/version.py` — Constitution §13 (depende de T121, T123, T125, T127)
- [ ] T131 [P] [US3] Test: `compute_fingerprint_set()` — determinismo ponta-a-ponta (mesma entrada duas vezes → `FingerprintSet` idêntico) em `tests/unit/test_fingerprint_set_determinism.py` — User Story 3 Acceptance Scenario 1 (depende de T130)

**Checkpoint (US3 completa)**: normalização + fingerprints determinísticos, versionados e independentes entre si, operando sobre a árvore agregada — base pronta para equivalência.

---

## Phase 7 — Exact Equivalence [US4]

**Propósito**: materializar `contracts/equivalence-contracts.md`. Inalterada.

- [ ] T132 [P] [US4] Test: `is_comparison_valid()` — mesmo scope, versões compatíveis, `collection_complete`, sem `critical_error`, sem challenge/tradução, snapshots aptos em `tests/unit/test_comparison_valid.py` — contracts/equivalence-contracts.md
- [ ] T133 [US4] Implementar `is_comparison_valid()` em `src/amayama_scraper/equivalence/validity.py` — mesma referência (depende de T132)
- [ ] T134 [P] [US4] Test: version mismatch (`normalizer_version`/`fingerprint_version`) produz `comparison_valid=False` e `UNKNOWN` — nunca `DIFFERENT` em `tests/unit/test_version_mismatch_unknown.py` — Constitution §13 (depende de T133)
- [ ] T135 [P] [US4] Test: `parts_relation` `EXACT`/`DIFFERENT`/`UNKNOWN` a partir de `spec_parts_hash` em `tests/unit/test_parts_relation.py` — FR-019
- [ ] T136 [US4] Implementar `evaluate_parts_relation()` em `src/amayama_scraper/equivalence/evaluate.py` — mesmas referências (depende de T133, T135)
- [ ] T137 [P] [US4] Test: `schema_relation` independente de `parts_relation` em `tests/unit/test_schema_relation.py` — contracts/equivalence-contracts.md
- [ ] T138 [US4] Implementar `evaluate_schema_relation()` em `src/amayama_scraper/equivalence/evaluate.py` — mesmas referências (depende de T136, T137)
- [ ] T139 [P] [US4] Test: `image_relation` (`EXACT`/`COMPLEMENTARY`/`DIFFERENT`/`NONE`/`UNKNOWN`) em `tests/unit/test_image_relation.py` — contracts/equivalence-contracts.md
- [ ] T140 [US4] Implementar `evaluate_image_relation()` em `src/amayama_scraper/equivalence/evaluate.py` — mesmas referências (depende de T138, T139)
- [ ] T141 [P] [US4] Test: `can_deduplicate()` só é `True` com `comparison_valid AND parts_relation == EXACT` em `tests/unit/test_can_deduplicate.py` — FR-019, FR-020
- [ ] T142 [US4] Implementar `can_deduplicate()` em `src/amayama_scraper/equivalence/evaluate.py` — mesmas referências (depende de T140, T141)
- [ ] T143 [P] [US4] Test: snapshots `INCOMPLETE`/`INVALID` nunca produzem `comparison_valid == True` em `tests/unit/test_incomplete_invalid_excluded.py` — FR-028 (depende de T133)
- [ ] T144 [P] [US4] Test: candidatos gerados por heurística nunca influenciam `can_deduplicate()` — apenas hash exato prova equivalência em `tests/unit/test_no_heuristic_as_proof.py` — FR-020 (depende de T142)

**Checkpoint (US4 parcial — equivalência)**: duas spec entries só são "equivalentes" quando a comparação é estritamente válida e o hash de peças é idêntico.

---

## Phase 8 — Clusters and Representative [US4]

**Propósito**: materializar Constitution §9 e `contracts/equivalence-contracts.md`. Inalterada.

- [ ] T145 [P] [US4] Test: `cluster_key` determinístico = `scope + normalizer_version + fingerprint_version + spec_parts_hash` em `tests/unit/test_cluster_key.py` — Constitution §9
- [ ] T146 [US4] Implementar `cluster_key()` em `src/amayama_scraper/equivalence/cluster.py` — mesma referência (depende de T145)
- [ ] T147 [P] [US4] Test: `EquivalenceClass` agrupa membros com mesmo `cluster_key`, preserva `member_spec_refs` (identidade nunca apagada) em `tests/unit/test_equivalence_class_membership.py` — FR-021
- [ ] T148 [US4] Implementar `build_equivalence_class()` em `src/amayama_scraper/equivalence/cluster.py` — mesmas referências (depende de T146, T147)
- [ ] T149 [P] [US4] Test: critério 1 (snapshot válido) desclassifica candidatos não-`VALID` em `tests/unit/test_representative_criterion_valid_snapshot.py` — Constitution §9
- [ ] T150 [P] [US4] Test: critério 2 (cobertura de imagens **próprias**, sem incluir fallback) em `tests/unit/test_representative_criterion_image_coverage.py` — research.md §12
- [ ] T151 [P] [US4] Test: critério 3 (catálogo mais atual via `collected_at`) em `tests/unit/test_representative_criterion_recency.py` — research.md §12
- [ ] T152 [P] [US4] Test: critério 4 (completude de metadados — proporção de campos preenchidos) em `tests/unit/test_representative_criterion_completeness.py` — research.md §12
- [ ] T153 [P] [US4] Test: critério 5 (`stable_key` como desempate final, comparação lexicográfica) em `tests/unit/test_representative_criterion_stable_key_tiebreak.py` — research.md §12
- [ ] T154 [US4] Implementar `select_representative()` aplicando os 5 critérios em ordem em `src/amayama_scraper/equivalence/representative.py` — mesmas referências (depende de T149–T153)
- [ ] T155 [P] [US4] Test: representante nunca redefine aplicabilidade — não-representantes continuam em `member_spec_refs` em `tests/unit/test_representative_does_not_redefine_applicability.py` — FR-021, FR-022 (depende de T154)
- [ ] T156 [P] [US4] Test: mudança em `spec_parts_hash` move a spec para outro `cluster_key` em `tests/unit/test_parts_hash_change_moves_cluster.py` — FR-031, SC-009 (depende de T146)
- [ ] T157 [P] [US4] Test: estrutura auxiliar tipo DSU/Union-Find (se usada) nunca é autoridade normativa — `cluster_key` recomputado é sempre a fonte da verdade em `tests/unit/test_cluster_key_is_normative.py` — ponto 14 do PLAN (depende de T146)

**Checkpoint (US4 completa)**: clusters formados exclusivamente por igualdade direta de conteúdo; representante determinístico; nenhuma identidade original é apagada.

---

## Phase 9 — Images and Provenance [US5]

**Propósito**: materializar `contracts/image-contract.md`. Inalterada.

- [ ] T158 [P] [US5] Test: imagem própria (`is_fallback=False`) quando a spec entry tem imagem própria em `tests/unit/test_image_own.py` — data-model.md §10
- [ ] T159 [US5] Implementar `resolve_image()` — caso imagem própria — em `src/amayama_scraper/assets/fallback.py` — mesma referência (depende de T045, T158)
- [ ] T160 [P] [US5] Test: fallback só ocorre dentro de cluster com `parts_relation == EXACT` comprovado em `tests/unit/test_image_fallback_requires_exact_cluster.py` — FR-023
- [ ] T161 [US5] Implementar `resolve_image()` — caso fallback, com `resolved_within_cluster_key` — em `src/amayama_scraper/assets/fallback.py` — mesma referência (depende de T159, T160)
- [ ] T162 [P] [US5] Test: fallback nunca ocorre entre specs sem equivalência comprovada em `tests/unit/test_image_fallback_rejected_without_equivalence.py` — FR-023 (depende de T161)
- [ ] T163 [P] [US5] Test: `origin_spec_ref` sempre preservado, inclusive em fallback — provenance nunca omitida em `tests/unit/test_image_provenance_preserved.py` — FR-024, FR-025 (depende de T161)
- [ ] T164 [P] [US5] Test: ausência de imagem resolvível retorna `None`, não é erro em `tests/unit/test_image_none_not_error.py` — data-model.md §10 (depende de T159)
- [ ] T165 [P] [US5] Test de integração: mudança só de imagem não move a spec para outro parts cluster (integra Phase 6/8) em `tests/integration/test_image_only_change_preserves_cluster.py` — FR-030, SC-009 (depende de T128, T156, T161)

**Checkpoint (US5 completa)**: cobertura de imagem tratada de forma independente da equivalência de peças; fallback controlado e sempre com proveniência.

---

## Phase 10 — Persistence

**Propósito**: implementar as escolhas técnicas de DEC-002 (research.md §8/§15) — SQLite para metadados/estado, filesystem content-addressed para raw. **Corrigido**: os repositórios de `RawBlob`/`RawCapture` agora são explicitamente *adapters* que satisfazem os ports definidos na Phase 2 (T029) — não módulos independentes que a Phase 3 dependesse ocultamente.

- [ ] T166 Implementar armazenamento de conteúdo endereçado por conteúdo (blob store, sharding de 2 níveis por `sha256`) em `src/amayama_scraper/persistence/blob_store.py` — research.md §8, data-model.md §4a
- [ ] T167 [P] Test: `blob_store` é idempotente — escrever o mesmo conteúdo duas vezes não duplica arquivo físico em `tests/unit/test_blob_store.py` — mesma referência (depende de T166)
- [ ] T168 Implementar helper de conexão/transação SQLite (`BEGIN IMMEDIATE`, escritor único) em `src/amayama_scraper/persistence/db.py` — research.md §8/§15
- [ ] T169 [P] Test: helper de transação faz rollback completo em exceção em `tests/unit/test_db_transaction_helper.py` — data-model.md §13c (depende de T168)
- [ ] T170 Implementar runner de migrations (aplica arquivos `.sql` versionados uma única vez) em `src/amayama_scraper/persistence/migrations/runner.py` — research.md §8
- [ ] T171 [P] Test: runner aplica migrations em ordem e nunca reaplica uma já aplicada em `tests/unit/test_migration_runner.py` — mesma referência (depende de T170)
- [ ] T172 [US1] Criar migration (`discovered_spec_entry`, `spec_registry`, `current_spec_state`) em `src/amayama_scraper/persistence/migrations/0001_spec_registry.sql` — data-model.md §1, §12, §14 (depende de T170)
- [ ] T173 [US1] Implementar `spec_registry_repo` (upsert por `stable_key`, leitura por `model_code`+`amayama_catalog_id`) + `discovered_spec_entry_repo` em `src/amayama_scraper/persistence/repositories/spec_registry_repo.py` — mesma referência (depende de T172)
- [ ] T174 [P] [US1] Test de integração: `spec_registry_repo` persiste e recupera `SpecIdentity`/`DiscoveredSpecEntry` em `tests/integration/test_spec_registry_repo.py` — data-model.md §1, §14 (depende de T173)
- [ ] T175 [US1] Criar migration (`spec_group_manifest`) em `src/amayama_scraper/persistence/migrations/0002_manifest.sql` — data-model.md §15 (depende de T170)
- [ ] T176 [US1] Implementar `manifest_repo`, incluindo `get_authoritative(spec_key, run_id) -> SpecGroupManifest | None` (aplica as 4 condições de autoridade de data-model.md §15) em `src/amayama_scraper/persistence/repositories/manifest_repo.py` — mesma referência (depende de T175)
- [ ] T177 [P] [US1] Test de integração: `manifest_repo` persiste e recupera `SpecGroupManifest`, preservando `manifest_complete`/`validation_evidence`; `get_authoritative()` retorna `None` quando qualquer condição de autoridade falha (captura não-`ACCEPTED`, `critical_error`, `manifest_complete=False`, ou grupo duplicado) e retorna o manifesto quando todas as condições são satisfeitas em `tests/integration/test_manifest_repo.py` — data-model.md §15 (depende de T176)
- [ ] T178 [US2] Criar migration (`raw_blob`, `raw_capture`) em `src/amayama_scraper/persistence/migrations/0003_raw.sql` — data-model.md §4a/§4b (depende de T170)
- [ ] T179 [US2] Implementar `FilesystemRawBlobStore` — satisfaz o port `RawBlobStore` (T029) usando `blob_store.py` (T166) — em `src/amayama_scraper/persistence/adapters/filesystem_raw_blob_store.py` — contracts/ports-contract.md; research.md §18 (depende de T029, T166, T178)
- [ ] T180 [US2] Implementar `SqliteRawCaptureRepository` — satisfaz o port `RawCaptureRepository` (T029) — em `src/amayama_scraper/persistence/adapters/sqlite_raw_capture_repository.py` — mesmas referências (depende de T029, T168, T178)
- [ ] T181 [P] [US2] Test de integração: `FilesystemRawBlobStore` + `SqliteRawCaptureRepository`, usados através de `accept_capture()` (Phase 3) sem qualquer alteração no código de `ingestion/` — dedup físico, observações distintas, **e replay**: `capture_repo.get(capture_id)` + `blob_store.read(content_hash)` reconstroem o `raw_content` original byte-a-byte a partir de uma instância nova dos repositórios (simulando restart) — em `tests/integration/test_raw_persistence_adapters.py` — data-model.md §4a/§4b/§13; contracts/ports-contract.md "Replay / Reconstrução determinística" (depende de T054, T179, T180)
- [ ] T182 [US7] Criar migration (`collection_run`, `checkpoint_entry` com `UNIQUE(run_id, spec_key, category_slug, group_id)`) em `src/amayama_scraper/persistence/migrations/0004_checkpoint.sql` — data-model.md §11/§13a (depende de T170)
- [ ] T183 [US7] Implementar `collection_run_repo` em `src/amayama_scraper/persistence/repositories/checkpoint_repo.py` — data-model.md §11 (depende de T182)
- [ ] T184 [US7] Implementar upsert de `checkpoint_entry` (`INSERT ... ON CONFLICT` sobre a chave única) **e** `list_accepted(run_id, spec_key) -> list[CheckpointEntry]` (todas as entradas `ACCEPTED` daquela spec entry naquela run, incluindo `raw_capture_id` de cada uma) em `src/amayama_scraper/persistence/repositories/checkpoint_repo.py` — data-model.md §11 "Leitura para replay", §13a (depende de T183)
- [ ] T185 [P] [US7] Test de integração: `checkpoint_repo` upsert idempotente — chamar duas vezes não duplica linha; `ACCEPTED` é terminal; `list_accepted()` retorna exatamente as entradas `ACCEPTED` (nunca `PENDING`/`IN_PROGRESS`/`REJECTED`), com `raw_capture_id` preservado, mesmo consultado a partir de uma instância nova do repositório (simulando restart) em `tests/integration/test_checkpoint_repo.py` — data-model.md §11, §13a (depende de T184)
- [ ] T186 [US6] Criar migration (`spec_snapshot` com `UNIQUE(idempotency_key)`) em `src/amayama_scraper/persistence/migrations/0005_snapshot.sql` — data-model.md §6/§13b (depende de T170)
- [ ] T187 [US6] Implementar `snapshot_repo` (insert-or-get por `idempotency_key`, transição `SUPERSEDED`) em `src/amayama_scraper/persistence/repositories/snapshot_repo.py` — mesma referência (depende de T186)
- [ ] T188 [P] [US6] Test de integração: `snapshot_repo` idempotente — mesmo `idempotency_key` não insere segunda linha em `tests/integration/test_snapshot_repo.py` — data-model.md §13b (depende de T187)
- [ ] T189 [US3] Criar migration (colunas de `FingerprintSet` associadas ao snapshot) em `src/amayama_scraper/persistence/migrations/0006_fingerprints.sql` — data-model.md §7 (depende de T170, T186)
- [ ] T190 [US3] Implementar `fingerprint_repo` em `src/amayama_scraper/persistence/repositories/fingerprint_repo.py` — mesma referência (depende de T189)
- [ ] T191 [US4] Criar migration (`cluster_assignment`) em `src/amayama_scraper/persistence/migrations/0007_clusters.sql` — data-model.md §9 (depende de T170)
- [ ] T192 [US4] Implementar `cluster_repo` (assignment por `normalizer_version`/`fingerprint_version`) em `src/amayama_scraper/persistence/repositories/cluster_repo.py` — mesma referência (depende de T191)
- [ ] T193 [P] [US4] Test de integração: `cluster_repo` invalida assignments antigos quando a versão muda em `tests/integration/test_cluster_repo.py` — data-model.md §9 (depende de T192)
- [ ] T194 [US5] Criar migration (`asset_resolution`) em `src/amayama_scraper/persistence/migrations/0008_assets.sql` — data-model.md §10 (depende de T170)
- [ ] T195 [US5] Implementar `asset_resolution_repo` em `src/amayama_scraper/persistence/repositories/asset_repo.py` — mesma referência (depende de T194)
- [ ] T196 [US1] Implementar materialização/consulta de `current_spec_state` (derivada de snapshot+cluster, reconstruível) em `src/amayama_scraper/persistence/repositories/current_state_repo.py` — data-model.md §12 (depende de T173, T187, T192)
- [ ] T197 [P] [US1] Test de integração: `current_state_repo` reflete o `SpecSnapshot` `VALID`/`STALE` mais recente e o `cluster_key` atual em `tests/integration/test_current_state_repo.py` — mesma referência (depende de T196)
- [ ] T198 Test de arquitetura: `persistence/` é o único módulo que importa `sqlite3`; nenhum módulo de domínio (`domain/`, `equivalence/`, `fingerprints/`, `normalization/`, `assets/`, `snapshots/`, `ingestion/`) o faz — `ingestion/` depende apenas dos ports (T029) em `tests/unit/test_persistence_isolation.py` — research.md §8/§18, Constitution §6
- [ ] T199 Documentar, em comentário de módulo de `src/amayama_scraper/persistence/db.py`, que PostgreSQL **não é projetado nesta feature** — apenas a fronteira de repositórios permite substituição futura (sem código de PostgreSQL) — DEC-002, research.md §8

**Checkpoint**: todo o estado do pipeline (descoberta, manifesto, identidade, raw, checkpoint, snapshot, fingerprints, clusters, imagens, current state) é persistível de forma auditável; `persistence/` isola SQL do domínio; os adapters de raw satisfazem os ports definidos na Phase 2 sem exigir qualquer mudança em `ingestion/`.

---

## Phase 11 — Checkpoint/Resume [US7]

**Propósito**: materializar a hierarquia de checkpoint sobre as entidades da Phase 2 e os repositórios da Phase 10. **Corrigido**: o universo de grupos "pendentes" é sempre derivado do `SpecGroupManifest` autoritativo (Phase 4/10), nunca inferido.

- [ ] T200 [P] [US7] Test: `upsert_checkpoint()` — transição `PENDING → IN_PROGRESS → ACCEPTED` em `tests/unit/test_checkpoint_transitions.py` — data-model.md §11
- [ ] T201 [US7] Implementar `upsert_checkpoint()` orquestrando `transition()` + `checkpoint_repo` em `src/amayama_scraper/checkpoint/upsert.py` — mesma referência (depende de T035, T184, T200)
- [ ] T202 [P] [US7] Test: captura `CHALLENGE`/`TRANSLATION_CONTAMINATED`/`INVALID`/`INCOMPLETE` nunca produz `ACCEPTED` (apenas `REJECTED` ou permanece `PENDING`) em `tests/unit/test_checkpoint_never_accepted_on_rejected_capture.py` — data-model.md §11 (depende de T201)
- [ ] T203 [P] [US7] Test: retry após `REJECTED` incrementa `attempt_count` e permite nova tentativa em `tests/unit/test_checkpoint_retry.py` — data-model.md §11 (depende de T201)
- [ ] T204 [P] [US7] Test de integração: `get_pending_groups()` deriva o universo esperado do `SpecGroupManifest` autoritativo (Phase 10) e retorna apenas `(category_slug, group_id)` ainda `PENDING`/`IN_PROGRESS`/`REJECTED` — nunca reprocessa `ACCEPTED` em `tests/integration/test_checkpoint_resume_skips_accepted.py` — FR-012, SC-004; data-model.md §15
- [ ] T205 [US7] Implementar `get_pending_groups(run_id, spec_key)` — consulta `manifest_repo` (T176) para o universo esperado e `checkpoint_repo` (T184) para o estado atual em `src/amayama_scraper/checkpoint/resume.py` — mesmas referências (depende de T176, T183, T204)
- [ ] T206 [P] [US7] Test: `category_slug` é usado apenas como índice — não possui status próprio (só `group_id` tem status) em `tests/unit/test_checkpoint_category_is_index_only.py` — data-model.md §11
- [ ] T207 [P] [US7] Test: `raw_capture_id` de um `CheckpointEntry` corresponde tipicamente a uma captura `GROUP_DETAIL` de um único grupo (research.md §16); o modelo continua permitindo compartilhamento entre grupos caso uma captura futura agregue mais de um em `tests/unit/test_checkpoint_capture_granularity.py` — research.md §16
- [ ] T208 [P] [US7] Test: `CollectionRun.scope` fixo (`AMAYAMA:VOLKSWAGEN:AMAROK:AMA-BR`) rejeita escopo divergente em `tests/unit/test_collection_run_scope.py` — FR-001, ponto 13 do PLAN

**Checkpoint (US7 completa)**: `Group` é a unidade mínima de progresso retomável, com o universo esperado sempre derivado do manifesto autoritativo; nada é reprocessado desnecessariamente; challenge nunca conclui um grupo.

---

## Phase 12 — Persistent Idempotency and Atomic Finalization [US6/US2]

**Propósito**: `idempotency_key` de snapshot e a transação de finalização (chave única + upsert já cobertos na Phase 10/11). **Corrigido**: `finalize_spec_entry()` agora exige explicitamente um manifesto autoritativo como precondição (contracts/snapshot-contract.md).

- [ ] T209 [P] [US6] Test: `accepted_checkpoint_fingerprint()` — multiset determinístico de `(category_slug, group_id, raw_capture_id)` `ACCEPTED` em `tests/unit/test_accepted_checkpoint_fingerprint.py` — data-model.md §13b
- [ ] T210 [US6] Implementar `accepted_checkpoint_fingerprint()` em `src/amayama_scraper/snapshots/idempotency.py` — mesma referência (depende de T209)
- [ ] T211 [P] [US6] Test: `idempotency_key` determinístico = `SHA256(run_id + spec_key + accepted_checkpoint_fingerprint)` em `tests/unit/test_idempotency_key.py` — data-model.md §13b
- [ ] T212 [US6] Implementar `compute_idempotency_key()` em `src/amayama_scraper/snapshots/idempotency.py` — mesma referência (depende de T210, T211)
- [ ] T213 [P] [US6] Test: retry da mesma finalização (mesmos `raw_capture_id` `ACCEPTED`) produz o mesmo `idempotency_key` em `tests/unit/test_idempotency_key_retry_stable.py` — data-model.md §13b (depende de T212)
- [ ] T214 [P] [US6] Test: nova coleta legítima (novo `raw_capture_id`, mesmo que conteúdo idêntico) produz `idempotency_key` diferente em `tests/unit/test_idempotency_key_new_capture_differs.py` — data-model.md §13b (depende de T212)
- [ ] T215 [P] [US6] Test: `finalize_spec_entry()` recusa executar (não gera snapshot) quando não existe manifesto autoritativo para `(spec_key, run_id)` em `tests/unit/test_finalize_requires_authoritative_manifest.py` — contracts/snapshot-contract.md PRECONDIÇÃO 1; data-model.md §15/§17
- [ ] T216 [US6] Implementar `finalize_spec_entry(spec_key, run_id)` — **corrigido**: sem parâmetro `assembled_tree` (nada pressupõe estado em memória). Fase 1 (leitura + computação, fora de transação de escrita): `manifest_repo.get_authoritative()` (T176) → `checkpoint_repo.list_accepted()` (T184) → para cada `CheckpointEntry` aceito, `capture_repo.get(raw_capture_id)` + `blob_store.read(content_hash)` (T029, adapters T179/T180) para recuperar `raw_content`, e `parse_group_detail()` (T086) para reconstruir cada `ParsedGroupDetail` — nenhum objeto parseado precisa ter sobrevivido de uma execução anterior; `assemble_spec_tree()` (T099) → `apply_normalization()` (T110) → `compute_fingerprint_set()` (T130) → `compute_idempotency_key()` (T212). Fase 2 (`BEGIN IMMEDIATE ... COMMIT`, T168): insert-or-get `SpecSnapshot` já com payload completo (T187), persistir `fingerprint_repo` (T190), superseder anterior, atualizar `current_spec_state` (T196), marcar conclusão — em `src/amayama_scraper/snapshots/finalize.py` — contracts/snapshot-contract.md; data-model.md §13c (depende de T086, T099, T110, T130, T168, T176, T184, T187, T190, T196, T212, T215)
- [ ] T217 [P] [US6] Test de integração: `finalize_spec_entry()` retry idempotente NÃO insere segundo `SpecSnapshot` em `tests/integration/test_finalize_idempotent_retry.py` — data-model.md §13b/§13c (depende de T216)
- [ ] T218 [P] [US6] Test de integração: `finalize_spec_entry()` com nova coleta legítima gera novo snapshot e supersede o anterior em `tests/integration/test_finalize_new_collection_supersedes.py` — FR-029, SC-008 (depende de T216)
- [ ] T219 [P] [US6] Test de integração: falha simulada durante a Fase 2 (transação de escrita) de `finalize_spec_entry()` faz rollback completo — sem snapshot órfão nem `current_spec_state` inconsistente; falha simulada durante a Fase 1 (reconstrução/parsing/fingerprint, ex. `RawBlob` ausente) nunca chega a abrir a transação — nenhum estado persistido é tocado, a finalização é re-tentável em `tests/integration/test_finalize_atomicity.py` — data-model.md §13c (depende de T216)
- [ ] T220 [P] [US2] Test de integração: duas `RawCapture` com mesmo `content_hash` em runs/momentos diferentes preservam provenance distinto e não colapsam a finalização em `tests/integration/test_raw_hash_equal_different_observations.py` — data-model.md §4b/§13b (depende de T181, T216)

**Checkpoint**: idempotência real garantida — nunca por content-addressing sozinho, mas por chave única + upsert + `idempotency_key` + transação única + manifesto autoritativo como precondição.

---

## Phase 13 — Snapshots and Revalidation [US6]

**Propósito**: materializar `contracts/snapshot-contract.md` e Constitution §11. **Corrigido**: `collection_complete` usa o manifesto (`expected ⊆ accepted`), não mais "todos os CheckpointEntry observados".

- [ ] T221 [P] [US6] Test: `collection_complete` — `True` se e somente se existe manifesto autoritativo e todo `(category_slug, group_id)` nele listado está `ACCEPTED`; `False` sem manifesto autoritativo, mesmo com `CheckpointEntry` `ACCEPTED` avulsos em `tests/unit/test_collection_complete_derivation.py` — contracts/snapshot-contract.md; data-model.md §17
- [ ] T222 [US6] Implementar `compute_collection_complete(manifest, checkpoint_entries)` em `src/amayama_scraper/snapshots/snapshot.py` — mesma referência (depende de T037, T221)
- [ ] T223 [P] [US6] Test: atribuição de `state` (`VALID`/`INCOMPLETE`/`INVALID`) conforme `critical_error`+`collection_complete` em `tests/unit/test_snapshot_state_assignment.py` — FR-027
- [ ] T224 [US6] Implementar `assign_snapshot_state()` em `src/amayama_scraper/snapshots/snapshot.py` — mesma referência (depende de T222, T223)
- [ ] T225 [P] [US6] Test de integração: `INCOMPLETE`/`INVALID` nunca participam de avaliação de equivalência (integra Phase 7) em `tests/integration/test_incomplete_invalid_excluded_from_equivalence.py` — FR-028 (depende de T143, T224)
- [ ] T226 [P] [US6] Test: falha de nova coleta não apaga/transiciona o último `VALID` conhecido (last-known-good) em `tests/unit/test_last_known_good_preserved.py` — FR-029, ponto 17 do PLAN (depende de T224)
- [ ] T227 [P] [US6] Test de integração: reprocessamento cria nova observação/snapshot, nunca sobrescreve (integra Phase 12) em `tests/integration/test_reprocessing_creates_new_snapshot.py` — FR-029, SC-008 (depende de T218)
- [ ] T228 [P] [US6] Test: revalidação incremental usa `structure_hash` primeiro, localiza divergência hierárquica antes de recomputar tudo em `tests/unit/test_incremental_revalidation.py` — FR-032, contracts/equivalence-contracts.md
- [ ] T229 [US6] Implementar `revalidate_spec_entry()` — top-down: `structure_hash` → fingerprints de category/group → decide `STALE`/reprocessar — em `src/amayama_scraper/snapshots/revalidation.py` — mesma referência (depende de T123, T228)
- [ ] T230 [P] [US6] Test: revalidação NUNCA afirma que um `Group` mudou sem recomputar seu `group_fingerprint` a partir de captura real (nenhum "validator" de terceira parte assumido) em `tests/unit/test_revalidation_requires_real_fetch.py` — ponto 18 do PLAN (depende de T229)
- [ ] T231 [US6] Implementar política de freshness como configuração (não constante rígida), diferenciando specs atuais/encerradas em `src/amayama_scraper/snapshots/freshness_policy.py` — Constitution §11
- [ ] T232 [P] [US6] Test: política de freshness é configurável e pode diferenciar specs atuais vs. encerradas em `tests/unit/test_freshness_policy_configurable.py` — mesma referência (depende de T231)
- [ ] T233 [US6] Implementar transição `VALID → STALE` quando revalidação detecta divergência sem nova captura ainda aceita em `src/amayama_scraper/snapshots/snapshot.py` — data-model.md §6 máquina de estados (depende de T037, T229)

**Checkpoint (US6 completa)**: snapshots imutáveis com estados corretos, `collection_complete` sempre ancorado no manifesto autoritativo; revalidação incremental sem afirmações não-evidenciadas; last-known-good nunca perdido.

---

## Phase 14 — Orchestration

**Propósito**: coordenar os módulos das Phases 3–13. **Corrigido**: roteia por `capture_kind` entre os três parsers, e agrega o processo de descoberta (Nível A) → manifesto (Nível B) → detalhe (Nível C) → finalização.

- [ ] T234 Implementar `process_capture(run_id, RawCaptureInput)` — roteia por `capture_kind`: `MARKET_INDEX` → `parse_market_spec_index()` (registra `DiscoveredSpecEntry`); `SPEC_NAVIGATION` → `parse_spec_group_manifest()` (registra `SpecGroupManifest`); `GROUP_DETAIL` → `parse_group_detail()` → normalization → fingerprints → `upsert_checkpoint()` — em `src/amayama_scraper/orchestration/pipeline.py` — plan.md pipeline conceitual; research.md §16 (depende de todas as Phases 3–11)
- [ ] T235 [P] Test de integração: `process_capture()` roteia corretamente cada `capture_kind` para o parser correspondente; `ACCEPTED` segue o pipeline completo; `CHALLENGE`/`TRANSLATION_CONTAMINATED`/`INVALID`/`INCOMPLETE` param antes de qualquer parser em `tests/integration/test_orchestration_routing.py` — contracts/input-contracts.md (depende de T234)
- [ ] T236 Implementar `try_finalize_spec_entry(run_id, spec_key)` — chamado após cada `GROUP_DETAIL` `ACCEPTED`, verifica via `get_pending_groups()` se o manifesto está totalmente coberto e, em caso afirmativo, chama `finalize_spec_entry()` (Phase 12) — em `src/amayama_scraper/orchestration/pipeline.py` — data-model.md §17 (depende de T205, T216, T234)
- [ ] T237 Implementar `run_collection(run_id, list[RawCaptureInput])` coordenando múltiplas capturas (dos três níveis) sob o mesmo `CollectionRun` em `src/amayama_scraper/orchestration/pipeline.py` — FR-001 (depende de T234)
- [ ] T238 [P] Test: `orchestration/` não duplica lógica de domínio — chama apenas funções de `validation/`, `parsing/`, `normalization/`, `fingerprints/`, `equivalence/`, `assets/`, `snapshots/`, `checkpoint/`, `persistence/`, sem reimplementar regras em `tests/unit/test_orchestration_no_duplicated_logic.py` — Constitution §6 (depende de T234)
- [ ] T239 [P] Test de salvaguarda: `orchestration/` não importa nenhuma biblioteca de automação de browser (Selenium/Playwright/CDP) em `tests/unit/test_no_browser_automation_dependency.py` — DEC-001, "Out of Scope" (depende de T234)

**Checkpoint**: pipeline completo executável offline, ponta-a-ponta, com os três níveis de captura corretamente roteados, sem qualquer componente de transporte automatizado.

---

## Phase 15 — Internal Export Boundary

**Propósito**: materializar `contracts/export-boundary-contract.md`. Inalterada.

- [ ] T240 [P] Test: `ExportView` preserva identidade, hierarquia, informação de cluster, `ResolvedImage` e referência de snapshot sem perda de dado em `tests/unit/test_export_view.py` — FR-033
- [ ] T241 Implementar `ExportView` (dataclass) em `src/amayama_scraper/export/view.py` — mesma referência (depende de T240)
- [ ] T242 Implementar `build_export_view(spec_entry, cluster, resolved_image, snapshot)` em `src/amayama_scraper/export/boundary.py` — mesma referência (depende de T241)
- [ ] T243 [P] Test: `export/` não importa nem referencia nenhum schema/pacote específico do Hubbi em `tests/unit/test_export_decoupled_from_hubbi.py` — FR-033, "Out of Scope" (depende de T242)
- [ ] T244 [P] Test: `export/` não expõe rota HTTP/API — nenhuma dependência de framework web em `tests/unit/test_no_http_api.py` — "Out of Scope" (depende de T242)

**Checkpoint**: saída interna pronta para uma futura integração Hubbi, sem acoplamento nesta feature.

---

## Phase 16 — Regression and Integration Tests

**Propósito**: fixar como fixtures/regressão os quatro casos de evidência já comprovados. **Corrigido**: fixtures refletem a granularidade real por `spec/category/group` (manifesto + páginas de detalhe individuais), não uma única "mega-página" por spec.

- [ ] T245 [P] [US4] Fixtures + regressão: `2HBC3X ↔ S1BC3X` produz `parts_relation == EXACT` — layout `tests/fixtures/regression/2hbc3x/manifest.html` + `tests/fixtures/regression/2hbc3x/<category>/<group>.html` (um arquivo por grupo real do par) espelhado em `tests/fixtures/regression/s1bc3x/` + `tests/regression/test_2hbc3x_s1bc3x.py` — SC-005
- [ ] T246 [P] [US4] Fixtures + regressão: `S6BC74 ↔ S7BC74` produz `parts_relation == EXACT`, diferença apenas de imagem — mesmo layout por `manifest.html` + `<category>/<group>.html` em `tests/fixtures/regression/{s6bc74,s7bc74}/` + `tests/regression/test_s6bc74_s7bc74.py` — SC-005
- [ ] T247 [P] [US4] Fixtures + regressão: `S7BC8A-62184 ↔ AGDC8A-62169` produz `parts_relation == EXACT`, imagens complementares — mesmo layout em `tests/fixtures/regression/{s7bc8a-62184,agdc8a-62169}/` + `tests/regression/test_s7bc8a_agdc8a.py` — SC-005
- [ ] T248 [P] [US1] Fixtures + regressão: `S7BC8A-61189` vs. outra entrada `S7BC8A` (catalog_id diferente) prova que `model_code` não é identidade suficiente — mesmo layout em `tests/fixtures/regression/s7bc8a-61189/` + `tests/regression/test_s7bc8a_model_code_not_unique.py` — FR-003, SC-002, SC-006
- [ ] T249 Revisão documental: registrar em `tests/regression/README.md` que (a) as fixtures acima refletem páginas reais capturadas por `spec/category/group`, nunca uma "mega-página" sintética — fixtures unitárias sintéticas usadas em outras fases (ex. Phase 4/6) devem ser explicitamente rotuladas como sintéticas; (b) nenhuma lógica de equivalência referencia os códigos `2H`/`S1`/`S6`/`S7`/`AGD`/`S7BC8A`/`AGDC8A` por string — os 4 testes acima validam comportamento emergente do conteúdo, nunca lógica hardcoded — ponto 25 do PLAN; ponto 10 desta revisão (depende de T136, T245–T248)
- [ ] T250 [P] Test de integração: pipeline completo `MARKET_INDEX` → `SPEC_NAVIGATION` → `GROUP_DETAIL`(s) → normalize → fingerprints → snapshot → equivalence → image resolution, offline, sem rede em `tests/integration/test_pipeline_end_to_end.py` — quickstart.md Cenário 10 (depende de T237)
- [ ] T251 [P] Test de integração: checkpoint/resume hierárquico completo (cenários A/B/C/D, incluindo ausência de manifesto autoritativo) **e Cenário E — restart real de processo**: persistir manifesto autoritativo; aceitar `Group A` e `Group B` (`CheckpointEntry.status == ACCEPTED`, cada um com seu `raw_capture_id`); descartar toda representação em memória (nenhuma referência a `ParsedGroupDetail`/árvore/manifesto do passo anterior); instanciar novos repositórios/serviços (simulando um processo novo); chamar `finalize_spec_entry(spec_key, run_id)` a partir dessa nova instância; verificar que `Group A` e `Group B` são reconstruídos exclusivamente via `manifest_repo.get_authoritative()` + `checkpoint_repo.list_accepted()` + `capture_repo.get()` + `blob_store.read()` + `parse_group_detail()`, que nenhum dos dois é recoletado, e que o `SpecSnapshot` resultante é `VALID` — em `tests/integration/test_checkpoint_resume_full.py` — quickstart.md Cenário 9; data-model.md §13c (depende de T176, T184, T204, T216)
- [ ] T252 [P] Test de integração: idempotência de checkpoint/snapshot e atomicidade de finalização, cenário completo em `tests/integration/test_idempotency_and_atomicity_full.py` — quickstart.md Cenário 11 (depende de T217–T220)
- [ ] T253 [P] [US1] Test de integração: enumeração completa via `MARKET_INDEX` (Cenário 0) até `SpecIdentity` registrada em `tests/integration/test_market_discovery_to_registry.py` — FR-001; quickstart.md Cenário 0 (depende de T075, T174)

**Checkpoint**: todos os casos de evidência documentados na spec estão fixados como regressão, refletindo a granularidade real da fonte; pipeline ponta-a-ponta validado offline, incluindo a enumeração (Nível A) antes ausente.

---

## Phase 17 — Quality and Documentation

**Propósito**: fechar a estratégia de qualidade/observabilidade sem infraestrutura de produção. Inalterada.

- [ ] T254 Configurar execução da suíte completa (`pytest --cov=amayama_scraper --cov-report=term-missing`) e limiar mínimo de cobertura para regras estruturais em `pyproject.toml` — Constitution §12
- [ ] T255 [P] Rodar `mypy --strict` sobre `src/` e corrigir eventuais erros de tipagem — research.md §3/§6
- [ ] T256 [P] Rodar `ruff check` + `ruff format --check` sobre `src/` e `tests/` — research.md §6
- [ ] T257 Documentar versões (`parser_version`, `normalizer_version`, `fingerprint_version`) em `docs/versions.md` — Constitution §13
- [ ] T258 Documentar o raw schema (`RawBlob`/`RawCapture`, `SpecGroupManifest`, layout do storage content-addressed) em `docs/raw-schema.md` — Constitution §4
- [ ] T259 Implementar logging estruturado (JSON lines, correlacionado por `run_id`, nunca despeja `raw_content` completo) em `src/amayama_scraper/orchestration/logging.py` — research.md §14
- [ ] T260 [P] Test: log nunca contém `raw_content` completo, apenas referência (`content_hash`/caminho) em `tests/unit/test_logging_no_raw_dump.py` — mesma referência (depende de T259)
- [ ] T261 Documentar identificadores de evidência/run (`run_id`, `capture_id`, evidência de checkpoint, evidência de manifesto) como contrato de observabilidade em `docs/observability.md` — ponto 27 do PLAN
- [ ] T262 Executar todos os cenários de `quickstart.md` como suíte de aceitação final e registrar o resultado em `docs/acceptance-report.md` (preenchido durante a implementação, não nesta fase TASKS) — quickstart.md

**Checkpoint final**: qualidade, tipagem, lint e observabilidade fechados; `quickstart.md` executável como critério de aceitação.

---

## Dependencies & Execution Order

### Dependências entre fases (bloqueantes)

- **Phase 1 (Setup)**: sem dependências.
- **Phase 2 (Domain Foundations)**: depende da Phase 1. **Bloqueia todas as fases seguintes.**
- **Phase 3 (Raw Ingestion/Validation)**: depende da Phase 2 (usa `RawBlob`/`RawCapture`/`CaptureValidationResult`/*ports*/fakes — **não** depende da Phase 10, graças aos ports).
- **Phase 4 (Parsing — 3 níveis)**: depende da Phase 2 e da Phase 3 (só processa capturas `ACCEPTED`).
- **Phase 5 (Normalization)**: depende da Phase 4.
- **Phase 6 (Fingerprints)**: depende da Phase 5 e da Phase 4 (`assemble_spec_tree`).
- **Phase 7 (Equivalence)**: depende da Phase 6.
- **Phase 8 (Clusters/Representative)**: depende da Phase 7.
- **Phase 9 (Images)**: depende da Phase 4 (imagem própria) e da Phase 7/8 (fallback).
- **Phase 10 (Persistence)**: depende apenas da Phase 2 (persiste as dataclasses/ports já definidos) — **pode rodar em paralelo com as Phases 3–9**, exceto os adapters de raw (T179/T180) que satisfazem os ports de Phase 2 e são exercitados por testes de integração que também tocam Phase 3 (T181).
- **Phase 11 (Checkpoint/Resume)**: depende da Phase 2, Phase 3, Phase 4 (manifesto) e Phase 10 (`checkpoint_repo`, `manifest_repo`).
- **Phase 12 (Idempotency/Finalization)**: depende da Phase 4 (`assemble_spec_tree`), Phase 6 (hashes), Phase 10 (`snapshot_repo`), Phase 11 (estado de checkpoint).
- **Phase 13 (Snapshots/Revalidation)**: depende da Phase 12 (finalização) e da Phase 6 (`structure_hash`).
- **Phase 14 (Orchestration)**: depende de **todas** as Phases 3–13.
- **Phase 15 (Export Boundary)**: depende da Phase 8, Phase 9 e Phase 13.
- **Phase 16 (Regression/Integration)**: depende de **todas** as Phases 3–15.
- **Phase 17 (Quality/Docs)**: roda por último.

### Paralelismo real (evitando paralelismo falso — correção desta revisão)

- Tasks que editam o **mesmo arquivo compartilhado** nunca são `[P]` entre si — corrigido explicitamente na Phase 1 (`pyproject.toml`), e aplicado consistentemente no restante do documento (ex. dentro de uma mesma migration `.sql`, dentro do mesmo módulo `evaluate.py`/`fallback.py`/`snapshot.py`/`pipeline.py` quando uma task estende a anterior).
- A Phase 10 é a maior oportunidade de paralelismo real em nível de fase — depende só da Phase 2, e roda em paralelo com as Phases 3–9 **exceto** pelos adapters de raw (T179/T180/T181), que têm dependência cruzada documentada com a Phase 3.
- As Phases 5→6→7→8 formam uma cadeia estritamente sequencial — não são paralelizáveis entre si.
- Tasks de teste e implementação do mesmo par não são paralelas entre si — o teste precede a implementação por definição.

### Ordem mínima para um vertical slice executável (US1)

1. Phase 1 (Setup)
2. Phase 2 (Domain Foundations, incluindo `DiscoveredSpecEntry`/`SpecGroupManifest`/ports)
3. Phase 3 (Raw Ingestion/Validation) — pré-requisito técnico de US1
4. Phase 4 (Parsing — os três níveis) — completa US1, incluindo FR-001 (Nível A)
5. Validação: `quickstart.md` Cenário 0, Cenário 1 e Cenário 3 executáveis

A partir daí, US3 (Phase 5–6), US4 (Phase 7–8), US5 (Phase 9), US7 (Phase 11) e US6 (Phase 12–13) são adicionadas incrementalmente, cada uma validável pelo cenário correspondente em `quickstart.md`.

---

## Rastreabilidade — Functional Requirements (FR-001 a FR-034)

| FR | Tasks |
|---|---|
| FR-001 | T015, T016, T073–T075, T208, T234, T237, T253 |
| FR-002 | T017, T018, T083, T084, T086, T172 |
| FR-003 | T013, T014, T015, T248 |
| FR-004 | T013, T014, T015, T172–T174 |
| FR-005 | T013, T014, T015, T087, T088 |
| FR-006 | T048 |
| FR-007 | T245–T249 |
| FR-008 | T025–T028, T053, T054 |
| FR-009 | T053, T054, T056, T057 |
| FR-010 | T058–T067, T091, T092 |
| FR-011 | T070, T071 |
| FR-012 | T200–T205, T221 |
| FR-013 | T021, T022, T083–T090 |
| FR-014 | T021, T022, T087, T088 |
| FR-015 | T100–T111 |
| FR-016 | T109 |
| FR-017 | T038, T039, T114, T115 |
| FR-018 | T126, T127, T158–T165 |
| FR-019 | T132–T136, T141, T142 |
| FR-020 | T144, T157 |
| FR-021 | T042, T043, T147, T148, T155 |
| FR-022 | T154 |
| FR-023 | T160–T162 |
| FR-024 | T163 |
| FR-025 | T163 |
| FR-026 | T172, T175–T177, T216, T221 |
| FR-027 | T036, T037, T223, T224 |
| FR-028 | T143, T225 |
| FR-029 | T187, T217–T219, T226, T227 |
| FR-030 | T128, T165 |
| FR-031 | T156 |
| FR-032 | T228–T230 |
| FR-033 | T240–T244 |
| FR-034 | T048, T050, T239 |

## Rastreabilidade — Success Criteria (SC-001 a SC-009)

| SC | Tasks |
|---|---|
| SC-001 | T013, T014, T174, T250 |
| SC-002 | T147, T248 |
| SC-003 | T058–T067 |
| SC-004 | T204, T251 |
| SC-005 | T245–T247 |
| SC-006 | T248 |
| SC-007 | T160, T163, T165 |
| SC-008 | T217–T219, T227 |
| SC-009 | T128, T156, T165 |

---

## Revisão de completude (autoavaliação antes da entrega)

- ✅ FR-001 é realmente implementável: `parse_market_spec_index()` (T073–T075), `DiscoveredSpecEntry` (T015–T016), persistência (T172–T174), roteamento em `run_collection()` (T237).
- ✅ Existe parser/contrato de market index (Nível A — T073–T075, contracts/domain-contracts.md).
- ✅ Existe parser/contrato de spec group manifest (Nível B — T076–T078, contracts/domain-contracts.md, data-model.md §15).
- ✅ Existe parser de group detail (Nível C — T079–T092).
- ✅ Expected groups têm fonte autoritativa: `SpecGroupManifest` + `is_manifest_authoritative()` (T019, T020), usada por `collection_complete` (T221–T222) e `get_pending_groups()` (T205).
- ✅ Captura parcial não pode resultar em `collection_complete=True`: T215 testa explicitamente a recusa de `finalize_spec_entry()` sem manifesto autoritativo.
- ✅ `RawBlobStore`/`RawCaptureRepository` (ports) existem documentalmente antes da persistência concreta: T029–T031 (Phase 2), consumidos por T054 (Phase 3), implementados como adapters em T179–T181 (Phase 10).
- ✅ Teste para `expected_identity_context`: T094 (teste) antes de T095 (implementação), cobrindo os 5 cenários pedidos.
- ✅ Nenhum falso `[P]` sobre o mesmo arquivo: Phase 1 corrigida (cadeia sequencial de `pyproject.toml`); revisão geral confirma que toda task `[P]` de implementação tem um arquivo de destino distinto de qualquer outra task `[P]` da mesma vizinhança.
- ✅ `category_slug` tem estratégia verificável: `extract_category_and_group_from_url()` (T081–T082), fundamentada em evidência de URL real, com gap remanescente registrado sem invenção (research.md §19).
- ✅ Fixtures de regressão refletem páginas reais por group: T245–T248 usam layout `manifest.html` + `<category>/<group>.html`, nunca uma mega-página.
- ✅ Nenhum Selenium/CDP: nenhuma task o menciona; salvaguardas explícitas em T072, T239.
- ✅ Nenhum bypass: T072 é salvaguarda explícita.
- ✅ Nenhuma integração produtiva Hubbi: T243 é salvaguarda explícita.
- ✅ Nenhuma implementação foi feita nesta revisão — apenas os artefatos documentais alterados/criados (ver relatório de entrega).
- ✅ DEC-001 (aquisição manual/browser-in-the-loop) materializada: T050 (`capture_kind`/`acquisition_mode`), T072/T239 (salvaguardas anti-automação).
- ✅ DEC-002 (persistência interna do MVP) materializada: T166–T199 (Phase 10 — SQLite + filesystem content-addressed, `RawBlobStore`/`RawCaptureRepository` adapters).
- ✅ DEC-003 (precedência de outcomes) materializada: T068 (teste) + T069 (implementação), contracts/input-contracts.md §2, research.md §20.
- ✅ Nenhum `[BLOQUEADA]` permanece no documento (verificado por busca textual).
- ✅ Checkpoint/resume sobrevive a restart de processo sem estado em memória: `finalize_spec_entry()` (T216) reconstrói `Group A`/`Group B` `ACCEPTED` exclusivamente via `manifest_repo.get_authoritative()` (T176), `checkpoint_repo.list_accepted()` (T184) e os ports `RawCaptureRepository.get()`/`RawBlobStore.read()` (T029, adapters T179/T180) — nenhum `ParsedGroupDetail` precisa sobreviver entre processos; cenário de restart real coberto por T251.

**Pendência resolvida**: a precedência de outcomes de validação quando múltiplos sinais coexistem simultaneamente foi aprovada pelo PO como **DEC-003** (`spec.md` §Decisions, 2026-08-26) — `CHALLENGE > TRANSLATION_CONTAMINATED > INVALID > INCOMPLETE > ACCEPTED`, com `evidence` sempre preservando todos os sinais detectados. A task antes bloqueada (T068) foi desbloqueada e decomposta em teste (T068) + implementação (T069). Nenhuma ambiguidade semântica pendente permanece nesta decomposição.

---

**Esta fase não avança para `/speckit-implement`.** `tasks.md` aguarda nova revisão da coordenação SDD e, em seguida, o gate explícito do Product Owner. TASKS aprovadas ainda **não** autorizam merge — a implementação só pode começar após novo approval explícito do PO.
