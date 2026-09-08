# Tasks: Scraper Real Amarok AMA-BR — Navegador Assistido, Human-in-the-Loop e Resume

**Feature**: `002-amarok-ama-br-browser-scraper` | **Branch**: `002-amarok-ama-br-browser-scraper`

**Input**: `spec.md` (aprovado + CLARIFY, DEC-001 a DEC-009), `plan.md` (aprovado), `research.md`, `data-model.md`, `quickstart.md`, `contracts/browser-transport-contract.md`, `contracts/orchestration-contract.md` — todos em `specs/002-amarok-ama-br-browser-scraper/`. Base adicional: código mergeado de `001-amarok-ama-br-ingestion`, GitHub Issue #10.

**Governança aplicada**: `.specify/memory/constitution.md`, `docs/sdd/EXECUTION_POLICY.md`, `AGENTS.md`, `CLAUDE.md`. Testes **não são opcionais** nesta feature — a instrução genérica do template Spec Kit ("Tests are OPTIONAL") é explicitamente ignorada, conforme `docs/sdd/EXECUTION_POLICY.md` §"Política de testes" e Constitution §12.

**Esta fase é exclusivamente de decomposição. Nenhuma task abaixo foi executada. `/speckit-implement` não foi disparado.**

## Convenções

- Formato: `- [ ] TXXX [P?] [USx?] Descrição em <arquivo> — refs: <FR/DEC/SC/contrato> ; depende de: <TYYY> ; conclusão: <critério objetivo>`
- `[P]` **somente** quando a task edita um arquivo diferente de qualquer outra task incompleta/concorrente e não depende do resultado dela. Tasks que tocam o mesmo arquivo nunca são `[P]`, mesmo que editem seções distintas.
- `[USx]` aplicado à task individual quando ela pertence claramente a uma User Story de `spec.md` (US1=descoberta real via navegador, US2=coleta automática de manifesto+grupos, US3=pausa human-in-the-loop em challenge, US4=resume sem recoleta, US5=controles operacionais seguros, US6=navegação conservadora). Fases de infraestrutura pura (1, 2, 3, 10, 11, 13) normalmente não carregam `[USx]`.
- Caminhos de arquivo são os alvos que a implementação futura deve criar/modificar — **nenhum deles existe ainda**, exceto os explicitamente marcados "MODIFICA" (arquivo já existe em `001`).
- Nenhuma task nesta lista implementa bypass de CAPTCHA/Cloudflare, stealth, anti-detecção, fingerprint spoofing, rotação de proxy para evasão, extração de token de challenge, ou manipulação artificial de cookies — qualquer task que sugerisse isso tornaria este `tasks.md` inválido (nenhuma o faz).

---

## Phase 1 — Baseline, dependência Selenium e contratos de transporte

**Propósito**: preparar a fronteira arquitetural (`transport/`), a regra "Selenium/CDP somente no adapter concreto", e os tipos base do transporte — antes de qualquer lógica de negócio nova. Nenhum Chrome real é tocado nesta fase.

- [x] T001 Adicionar `selenium>=4.15,<5` a `[project] dependencies` em `pyproject.toml` (MODIFICA) — refs: research.md §14, plan.md "Dependências novas" ; conclusão: `pip install -e .[dev]` resolve `selenium` sem erro; nenhuma outra dependência de automação (`playwright`/`pyppeteer`/`undetected-chromedriver`/`selenium-stealth`) é adicionada.
- [x] T002 [P] Criar pacote `src/amayama_scraper/transport/__init__.py` (vazio) — refs: plan.md "Project Structure" ; conclusão: pacote importável.
- [x] T003 [P] Test: `BrowserCapture` — imutável (`frozen`), campos `page_source`/`effective_url`/`captured_at` obrigatórios, em `tests/unit/test_browser_capture.py` — refs: data-model.md §1 ; conclusão: teste falha antes da implementação (T004 ausente) e cobre a forma exata do dataclass.
- [x] T004 Implementar `BrowserCapture` em `src/amayama_scraper/transport/port.py` — refs: mesmas de T003 ; depende de: T002, T003 ; conclusão: T003 passa.
- [x] T005 [P] Test: `BrowserTransport` — Protocol estrutural (`navigate`/`current_capture`), verificado por um objeto de teste mínimo satisfazendo o Protocol, em `tests/unit/test_browser_transport_protocol.py` — refs: contracts/browser-transport-contract.md §1 ; conclusão: `mypy --strict` aceita o objeto de teste como `BrowserTransport` sem cast.
- [x] T006 Implementar `BrowserTransport` (Protocol) em `src/amayama_scraper/transport/port.py` (mesmo arquivo de T004) — refs: mesmas de T005 ; depende de: T004, T005 ; conclusão: T005 passa.
- [x] T007 [P] Test: hierarquia de exceções `TransportError`/`ChromeNotReachableError`/`NavigationTimeoutError`/`NavigationFailedError` — todas subclasses de `TransportError`, nenhuma é/estende `ValidationOutcome` em `tests/unit/test_transport_errors.py` — refs: data-model.md §3, DEC-006 ; conclusão: teste comprova isolamento de hierarquias (`issubclass` cruzado falha).
- [x] T008 Implementar `transport/errors.py` com a hierarquia acima — refs: mesmas de T007 ; depende de: T002, T007 ; conclusão: T007 passa.
- [x] T009 [P] Test: `FakeBrowserTransport` — permite programar uma sequência de respostas (`BrowserCapture` ou exceção) por chamada, satisfaz `BrowserTransport` estruturalmente, em `tests/unit/test_ports_fakes.py` (estendido) — refs: quickstart.md pré-requisitos, contracts/browser-transport-contract.md §1 ; conclusão: teste cobre navegação com sucesso, navegação com exceção agendada, e `current_capture()` sem nova navegação.
- [x] T010 Implementar `FakeBrowserTransport` em `tests/unit/fakes.py` (MODIFICA) — refs: mesmas de T009 ; depende de: T006, T008, T009 ; conclusão: T009 passa.
- [x] T011 [P] Test: fronteira de arquitetura — `selenium` é importável **somente** por `src/amayama_scraper/transport/chrome_cdp_adapter.py`; nenhum outro arquivo de `src/` (incluindo `transport/port.py`, `transport/errors.py`, `orchestration/pipeline.py`, todo o domain layer) o importa; `pyproject.toml` declara `selenium` mas não `playwright`/`pyppeteer`/`undetected-chromedriver`/`selenium-stealth` — em `tests/unit/test_no_browser_automation_dependency.py` (MODIFICA — substitui a proibição cega por uma allowlist de um único arquivo) — refs: research.md §13, Constitution §5/§6 ; conclusão: teste falha se `selenium` for importado fora de `chrome_cdp_adapter.py`, e falha se qualquer dependência de stealth/automação adicional for declarada.
- [x] T012 Ajustar `tests/unit/test_no_browser_automation_dependency.py` para a allowlist descrita em T011 — refs: mesmas de T011 ; depende de: T001, T002, T011 ; conclusão: T011 passa; a invariante original (nenhuma lógica de domínio toca Selenium) continua 100% verificada, apenas com escopo mais preciso.
- [x] T013 [P] Test: `test_architecture_boundaries.py` — confirmar que `transport/` **não** está em `DOMAIN_LAYER_PACKAGES` (não precisa mudar) e adicionar caso explícito de que `orchestration.pipeline` (arquivo, não pacote) segue sem importar `amayama_scraper.transport` — em `tests/unit/test_architecture_boundaries.py` (MODIFICA, adição pontual) — refs: research.md §5, §13 ; depende de: T002 ; conclusão: teste falha se `orchestration/pipeline.py` importar `transport` no futuro.

**Checkpoint**: fronteira de transporte existe (tipos + fake), a regra "Selenium somente no adapter" é verificada automaticamente, `pipeline.py` de `001` permanece intocado e comprovadamente livre de `transport`/`selenium`.

---

## Phase 2 — Adapter Chrome/CDP concreto

**Propósito**: `ChromeCdpTransport`, único ponto de contato real com Selenium/CDP. Testado inteiramente com stubs — nenhum Chrome real é aberto pela suíte automatizada.

- [x] T014 [P] Test: resolução de endereço CDP — precedência CLI-arg > env (`AMAYAMA_CDP_HOST`/`AMAYAMA_CDP_PORT`) > default `127.0.0.1:9222`, em `tests/unit/test_chrome_cdp_adapter.py` — refs: research.md §3 ; conclusão: as três fontes são testadas isoladamente e em combinação.
- [x] T015 Implementar resolução de endereço CDP em `src/amayama_scraper/transport/chrome_cdp_adapter.py` — refs: mesmas de T014 ; depende de: T001, T002, T014 ; conclusão: T014 passa.
- [x] T016 [P] Test: `ChromeCdpTransport.__init__` — fail-fast com `ChromeNotReachableError` quando `http://{host}:{port}/json/version` não responde (stub de `selenium`/`urllib` via monkeypatch, nunca rede real), em `tests/unit/test_chrome_cdp_adapter.py` — refs: research.md §4, contracts/browser-transport-contract.md §2 ; conclusão: teste comprova que nenhuma tentativa de lançar um processo de Chrome ocorre nesse caminho.
- [x] T017 Implementar verificação fail-fast de conectividade no construtor de `ChromeCdpTransport` — refs: mesmas de T016 ; depende de: T008, T015, T016 ; conclusão: T016 passa.
- [x] T018 [P] Test: `ChromeCdpTransport.navigate(url)` — usa `debuggerAddress` (Selenium `Options.add_experimental_option`) para anexar, nunca `webdriver.Chrome()` em modo de lançamento; retorna `BrowserCapture` com `page_source`/`effective_url`/`captured_at` reais do driver stubado, em `tests/unit/test_chrome_cdp_adapter.py` — refs: research.md §2, contracts/browser-transport-contract.md §2 ; conclusão: teste verifica que o construtor do stub de `webdriver.Chrome` recebe `debuggerAddress`, nunca é chamado para lançar um novo processo.
- [x] T019 Implementar `navigate()` em `ChromeCdpTransport` — refs: mesmas de T018 ; depende de: T004, T006, T017, T018 ; conclusão: T018 passa.
- [x] T020 [P] Test: `ChromeCdpTransport.current_capture()` — relê `page_source`/URL atual **sem** chamar `navigate`/`get(url)` do driver, em `tests/unit/test_chrome_cdp_adapter.py` — refs: contracts/browser-transport-contract.md §1 (research.md §11) ; conclusão: teste comprova zero chamada de navegação no stub.
- [x] T021 Implementar `current_capture()` em `ChromeCdpTransport` — refs: mesmas de T020 ; depende de: T019, T020 ; conclusão: T020 passa.
- [x] T022 [P] Test: retry interno de falha de transporte — `navigate()` tenta até `max_retries` (configurável) com backoff configurável antes de levantar `NavigationFailedError`/`NavigationTimeoutError`; sucesso em uma tentativa intermediária não propaga exceção, em `tests/unit/test_chrome_cdp_adapter.py` — refs: research.md §10, spec.md FR-020.1 ; conclusão: teste cobre esgotamento de tentativas e sucesso após falha transitória, ambos sem número fixo não-configurável.
- [x] T023 Implementar retry interno configurável (`max_retries`, `backoff_seconds`) em `navigate()`/`current_capture()` — refs: mesmas de T022 ; depende de: T019, T021, T022 ; conclusão: T022 passa; nenhum retry é acionado para falhas que já produziram uma `BrowserCapture` válida (essas nunca são "falha").

**Checkpoint**: `ChromeCdpTransport` existe, satisfaz `BrowserTransport`, nunca lança/gerencia um processo de Chrome, nunca implementa CAPTCHA/stealth/proxy/tokens, e é 100% testável sem Chrome real.

---

## Phase 3 — Persistência operacional (sem migration)

**Propósito**: as duas leituras aditivas + o ajuste de conexão exigidos por DEC-005/concorrência, e o único valor de enum novo. **Nenhuma migration é criada** — se, ao implementar, ficar provado que o schema atual não atende, a implementação deve **parar e reportar como blocker ao PO**, nunca inventar uma migration silenciosamente.

- [x] T024 [P] Test: `AcquisitionMode.AUTOMATED_BROWSER_CDP` existe, `RawCaptureInput`/`accept_capture()`/`process_capture()` aceitam-no sem ramificação especial (paridade com `MANUAL_BROWSER`), em `tests/unit/test_raw_capture_input.py` (extensão) — refs: data-model.md §0, research.md §6 ; conclusão: uma `RawCaptureInput` com `acquisition_mode=AUTOMATED_BROWSER_CDP` produz o mesmo comportamento de `accept_capture()` que uma com `MANUAL_BROWSER`, byte a byte de raw preservado.
- [x] T025 Adicionar `AUTOMATED_BROWSER_CDP` a `AcquisitionMode` em `src/amayama_scraper/ingestion/capture_kind.py` (MODIFICA — um único novo membro de enum) — refs: mesmas de T024 ; depende de: T024 ; conclusão: T024 passa; nenhuma outra linha de `capture_kind.py` é alterada.
- [x] T026 [P] Test: `list_incomplete_runs(conn, scope)` — retorna apenas `CollectionRun` com `scope` igual e `completed_at IS NULL`; run completo não aparece; run de outro `scope` não aparece; ordenação estável (mais antigo primeiro), em `tests/integration/test_checkpoint_repo.py` (extensão, SQLite real em arquivo temporário) — refs: data-model.md §7, DEC-005, contracts/orchestration-contract.md §1 ; conclusão: cobre 0/1/2+ resultados e o caso de exclusão por `scope`/`completed_at`.
- [x] T027 Implementar `list_incomplete_runs()` em `src/amayama_scraper/persistence/repositories/checkpoint_repo.py` (MODIFICA — nova função, nenhuma existente alterada) — refs: mesmas de T026 ; depende de: T026 ; conclusão: T026 passa; `get_collection_run`/`save_collection_run`/`upsert_checkpoint_entry`/`get_checkpoint_entry`/`list_accepted` permanecem byte-a-byte idênticas.
- [x] T028 [P] Test: `list_all_spec_identities(conn)` — retorna todas as `SpecIdentity` de `spec_registry`, independente de `run_id`; lista vazia quando nada foi descoberto ainda, em `tests/integration/test_spec_registry_repo.py` (extensão) — refs: data-model.md §7, research.md §12 ; conclusão: cobre 0/1/N specs e reflete exatamente o que `save_spec_identity()` já persistiu.
- [x] T029 Implementar `list_all_spec_identities()` em `src/amayama_scraper/persistence/repositories/spec_registry_repo.py` (MODIFICA — nova função) — refs: mesmas de T028 ; depende de: T028 ; conclusão: T028 passa; `save_spec_identity`/`get_spec_identity`/`find_by_model_code_and_catalog_id`/`save_discovered_spec_entry`/`list_discovered_spec_entries` permanecem inalteradas.
- [x] T030 [P] Test: `connect()` define `PRAGMA busy_timeout = 5000` — verificado via `conn.execute("PRAGMA busy_timeout").fetchone()`, em `tests/unit/test_db_transaction_helper.py` (extensão) — refs: data-model.md §8, research.md §16 ; conclusão: valor configurado é lido de volta corretamente; nenhum outro `PRAGMA`/comportamento de `connect()` muda.
- [x] T031 Adicionar `PRAGMA busy_timeout = 5000` a `connect()` em `src/amayama_scraper/persistence/db.py` (MODIFICA — uma linha) — refs: mesmas de T030 ; depende de: T030 ; conclusão: T030 passa.
- [x] T032 Auditoria/checkpoint explícito: confirmar que `src/amayama_scraper/persistence/migrations/` continua com exatamente os 8 arquivos de `001` (nenhuma migration nova) — refs: spec.md FR-032, plan.md "Persistência/migrations — confirmação" ; depende de: T027, T029, T031 ; conclusão: `ls src/amayama_scraper/persistence/migrations/*.sql | wc -l` permanece 8. **Se, neste ponto da implementação, alguma task desta fase provar que uma migration é necessária, a task correspondente deve ser marcada como bloqueada e reportada ao PO — nunca resolvida silenciosamente com uma migration não planejada.**

**Checkpoint**: as duas leituras aditivas e o ajuste de `busy_timeout` existem e são testados sobre SQLite real; nenhuma migration foi criada; o enum de aquisição cobre o transporte automatizado sem tocar nenhuma lógica existente.

---

## Phase 4 — Seleção de run / resume (DEC-005) [US4]

**Propósito**: `orchestration/run_selection.py::select_run()` — função pura, algoritmo de 3 ramos, nunca escolhe heuristicamente entre execuções incompletas concorrentes.

- [x] T033 [P] [US4] Test: `select_run()` — zero `CollectionRun` incompleta compatível → cria e persiste uma nova (via `save_collection_run` injetado), `created_new=True`, em `tests/unit/test_run_selection.py` — refs: FR-019, FR-026, DEC-005, contracts/orchestration-contract.md §1 ; conclusão: `save_collection_run` é chamado exatamente uma vez com um `CollectionRun` de `scope` correto.
- [x] T034 [P] [US4] Test: `select_run()` — exatamente uma incompleta compatível → resume automaticamente, `created_new=False`, **nenhuma** chamada a `save_collection_run`, em `tests/unit/test_run_selection.py` — refs: mesmas de T033 ; conclusão: `save_collection_run` nunca é invocado neste ramo.
- [x] T035 [P] [US4] Test: `select_run()` — duas ou mais incompletas compatíveis → `AmbiguousResumeError` contendo a lista de candidatos, nenhuma escrita, em `tests/unit/test_run_selection.py` — refs: mesmas de T033 ; conclusão: exceção carrega todos os candidatos; nenhuma heurística de desempate é aplicada em nenhum teste.
- [x] T036 [P] [US4] Test: `select_run(resume_run_id=...)` — `run_id` existente e compatível (`scope` igual, `completed_at is None`) → retorna esse run sem gravar nada, em `tests/unit/test_run_selection.py` — refs: mesmas de T033 ; conclusão: `get_collection_run` chamado, `save_collection_run` nunca chamado.
- [x] T037 [P] [US4] Test: `select_run(resume_run_id=...)` — `run_id` de `scope` incompatível OU já `completed_at` preenchido OU inexistente → `IncompatibleResumeRunError`, em `tests/unit/test_run_selection.py` — refs: mesmas de T033 ; conclusão: os três subcasos (scope diferente / completo / inexistente) são cobertos separadamente.
- [x] T038 [P] [US4] Test: `select_run(new_run=True)` — sempre cria novo run mesmo havendo uma incompleta compatível, nunca toca a existente, em `tests/unit/test_run_selection.py` — refs: mesmas de T033 ; conclusão: a incompleta pré-existente permanece com seu estado original (nenhuma chamada de leitura/escrita sobre ela).
- [x] T039 [US4] Implementar `RunSelectionResult`, `IncompatibleResumeRunError`, `AmbiguousResumeError`, `select_run()` em `src/amayama_scraper/orchestration/run_selection.py` — refs: contracts/orchestration-contract.md §1 ; depende de: T033, T034, T035, T036, T037, T038 ; conclusão: T033–T038 passam; módulo não importa `sqlite3` nem `selenium` (função pura sobre callables injetadas).
- [x] T040 [US4] Test de integração: `select_run()` sobre SQLite real (`checkpoint_repo.list_incomplete_runs`/`get_collection_run`/`save_collection_run` reais) reproduzindo os 6 cenários acima ponta a ponta, em `tests/integration/test_run_selection_sqlite.py` — refs: mesmas de T033, plan.md "Modelo de run/resume" ; depende de: T027, T039 ; conclusão: mesmos resultados dos testes unitários, agora contra o banco real.
- [x] T041 [US4] Test de integração: semântica de restart — encerrar o processo (simulado: nova conexão SQLite, nenhum estado Python reaproveitado) no meio de uma spec com `run_id` conhecido, e confirmar que `select_run(resume_run_id=run_id)` reconstrói a decisão inteiramente a partir do estado persistido (não de memória), em `tests/integration/test_resume_after_restart_semantics.py` — refs: FR-018, SC-003, spec.md Edge Cases ; depende de: T040 ; conclusão: uma segunda conexão/processo simulado chega à mesma decisão de resume que o processo original teria.

**Checkpoint**: seleção de run é determinística, testada em memória e contra SQLite real, e comprovadamente nunca escolhe heuristicamente entre execuções ambíguas.

---

## Phase 5 — Retry: transporte vs. rejeição de validação (DEC-006)

**Propósito**: `orchestration/retry_classification.py` — separação formal entre falha de transporte (retry automático configurável) e rejeição de `classify_capture()` (nunca automática).

- [x] T042 [P] Test: `classify_pending_unit(None)` e `classify_pending_unit(<PENDING>)` → `NOT_YET_ATTEMPTED`, em `tests/unit/test_retry_classification.py` — refs: DEC-006, contracts/orchestration-contract.md §2 ; conclusão: ambos os casos cobertos.
- [x] T043 [P] Test: `classify_pending_unit(<IN_PROGRESS>)` → `TRANSPORT_RETRY`, em `tests/unit/test_retry_classification.py` — refs: mesmas de T042 ; conclusão: cobre uma entrada órfã (sem `raw_capture_id`).
- [x] T044 [P] Test: `classify_pending_unit(<REJECTED, evidence={"outcome": "CHALLENGE"}>)` → `CHALLENGE_PAUSED`, em `tests/unit/test_retry_classification.py` — refs: mesmas de T042 ; conclusão: apenas `outcome == "CHALLENGE"` produz essa classificação.
- [x] T045 [P] Test: `classify_pending_unit(<REJECTED, evidence={"outcome": "INVALID"|"INCOMPLETE"|"TRANSLATION_CONTAMINATED"}>)` e `classify_pending_unit(<REJECTED, evidence={"critical_error": ...}>)` → `REQUIRES_EXPLICIT_RETRY` em todos os casos, em `tests/unit/test_retry_classification.py` — refs: mesmas de T042 ; conclusão: os 4 subcasos (3 outcomes + critical_error) são testados individualmente.
- [x] T046 [US3] Implementar `PendingUnitClassification` + `classify_pending_unit()` em `src/amayama_scraper/orchestration/retry_classification.py` — refs: contracts/orchestration-contract.md §2 ; depende de: T042, T043, T044, T045 ; conclusão: T042–T045 passam; módulo é síncrono, sem I/O, sem novo `CheckpointStatus`.
- [x] T047 [P] Test: transição `REJECTED → IN_PROGRESS` via `START_ATTEMPT` já é permitida pela máquina de estados existente — teste de **regressão/confirmação** (não nova funcionalidade) em `tests/unit/test_checkpoint_transitions.py` (extensão) — refs: research.md §9 ; conclusão: prova documentada de que nenhuma mudança em `checkpoint/checkpoint_entry.py` é necessária para DEC-006.
- [x] T048 [US3] Test: driver — por padrão, unidades `REQUIRES_EXPLICIT_RETRY` são excluídas da passada corrente; com o filtro de retry manual ativo, são incluídas (emitindo `START_ATTEMPT` normalmente), em `tests/unit/test_retry_gate_default_vs_explicit.py` — refs: FR-020, spec.md DEC-006 ; depende de: T046 ; conclusão: uma função `filter_units_for_pass(classification, *, retry_rejected: bool)` (ou equivalente) decide isso, testável isoladamente sem depender do driver completo.
- [x] T049 [US3] Implementar o filtro de inclusão por passada (`filter_units_for_pass()` ou equivalente) — pode viver em `retry_classification.py` — refs: mesmas de T048 ; depende de: T048 ; conclusão: T048 passa.
- [x] T050 [US3] Test de integração: falha de transporte (exceção de `FakeBrowserTransport`) nunca produz um `CheckpointEntry` com `evidence.outcome` — permanece `IN_PROGRESS`, reclassificada como `TRANSPORT_RETRY` na próxima leitura, em `tests/integration/test_transport_failure_never_becomes_validation_rejection.py` — refs: data-model.md §3, DEC-006 ; depende de: T023, T046 ; conclusão: nenhuma chamada a `classify_capture()`/`process_capture()` ocorre quando o transporte falha antes de produzir uma `BrowserCapture`.
- [x] T051 [US3] Test de integração: `attempt_count` incrementa a cada `START_ATTEMPT` em unidades órfãs/retentadas, servindo como auditoria combinada de tentativas (transporte + validação), em `tests/integration/test_checkpoint_repo.py` (extensão) — refs: research.md §10 ; depende de: T027, T046 ; conclusão: sequência de 3 tentativas produz `attempt_count == 3`.

**Checkpoint**: retry de transporte e rejeição de validação nunca se misturam; nenhuma nova transição de estado foi necessária; a exclusão de `REQUIRES_EXPLICIT_RETRY` do fluxo automático é testável isoladamente do driver completo.

---

## Phase 6 — Challenge human-in-the-loop [US3]

**Propósito**: laço de pausa/retomada (`await_challenge_resolution()`), reutilizando `classify_capture()`/`route_if_challenge()` reais em cada verificação — nunca uma decisão paralela.

- [x] T052 [P] [US3] Test: `await_challenge_resolution()` — `FakeBrowserTransport` devolve challenge nas primeiras K leituras de `current_capture()` e página válida na (K+1)-ésima; a função só retorna após `process_capture()` deixar de reportar `CHALLENGE`, em `tests/integration/test_challenge_pause_and_resume.py` — refs: FR-011, FR-012, SC-005, contracts/browser-transport-contract.md §4 ; conclusão: nenhuma chamada intermediária marca a unidade `ACCEPTED`.
- [x] T053 [P] [US3] Test: intervalo de poll é respeitado e configurável (`poll_interval`) — usando um relógio/`sleep` injetado (nunca `time.sleep` real em teste), em `tests/unit/test_challenge_poll_interval.py` — refs: research.md §11, FR-012 ; conclusão: número de leituras observadas corresponde ao tempo simulado / intervalo configurado.
- [x] T054 [P] [US3] Test: `--challenge-timeout` opcional — quando definido e excedido, a função desiste **apenas daquela unidade** (retorna sem sucesso, unidade permanece `REJECTED`/`CHALLENGE`), sem abortar a execução; quando ausente (default), espera indefinidamente (verificado até um número grande de iterações simuladas sem desistir), em `tests/unit/test_challenge_timeout.py` — refs: research.md §11 ; conclusão: os dois modos (com/sem timeout) são cobertos separadamente.
- [x] T055 [US3] Implementar `await_challenge_resolution()` em `src/amayama_scraper/orchestration/collection_driver.py` — refs: contracts/browser-transport-contract.md §4 ; depende de: T006, T010, T046, T052, T053, T054 ; conclusão: T052–T054 passam.
- [x] T056 [P] [US3] Test: challenge no nível `MARKET_INDEX` — pausa antes de qualquer spec ser descoberta, retoma e a descoberta prossegue normalmente após resolução, em `tests/integration/test_challenge_pause_and_resume.py` (caso adicional) — refs: spec.md Edge Cases, US3 cenário 1 ; depende de: T055 ; conclusão: `list_all_spec_identities()` fica vazia durante a pausa e populada após a resolução.
- [x] T057 [P] [US3] Test: challenge no nível `SPEC_NAVIGATION` — pausa antes do manifesto existir, retoma e o manifesto autoritativo é persistido após resolução, em `tests/integration/test_challenge_pause_and_resume.py` (caso adicional) — refs: mesmas de T056 ; depende de: T055 ; conclusão: `get_authoritative()` retorna `None` durante a pausa e o manifesto real após.
- [x] T058 [P] [US3] Test: challenge no nível `GROUP_DETAIL` — pausa sem afetar grupos já `ACCEPTED` da mesma spec, retoma e o grupo pausado (só ele) transiciona, em `tests/integration/test_challenge_pause_and_resume.py` (caso adicional) — refs: mesmas de T056, US3 cenário 3 ; depende de: T055 ; conclusão: `list_accepted()` antes/depois difere apenas na unidade que estava pausada.
- [x] T059 [P] [US3] Test: Chrome fechado durante a espera — `current_capture()` levanta `ChromeNotReachableError`, a função propaga (não engole) a exceção, execução é interrompida com a unidade preservada em estado retomável, em `tests/integration/test_challenge_chrome_lost_during_wait.py` — refs: research.md §11, spec.md Edge Cases ; depende de: T055 ; conclusão: nenhuma escrita adicional ocorre após a exceção; `CheckpointEntry` permanece exatamente como estava antes da espera.
- [x] T060 [US3] Test: página errada após resolução — o operador "navega" (via fake) para uma página que não corresponde ao `capture_kind` esperado; `detect_invalid_structure()` real produz `INVALID`; a unidade vira `REQUIRES_EXPLICIT_RETRY` e o laço não reentra automaticamente em novo poll para ela, em `tests/integration/test_challenge_wrong_page_after_resolution.py` — refs: contracts/browser-transport-contract.md §4, research.md §11 ; depende de: T046, T055 ; conclusão: nenhum detector novo é criado — o teste usa `detect_invalid_structure()` já existente sem modificação.
- [x] T061 [US3] Test: challenge persistindo indefinidamente sob `--challenge-timeout` não configurado — simular N iterações de poll todas retornando challenge, confirmar que a função nunca desiste sozinha (só interrompida externamente/por timeout explícito), em `tests/unit/test_challenge_persists_without_timeout.py` — refs: research.md §11 ; depende de: T055 ; conclusão: após N iterações simuladas, a unidade continua sem outcome diferente de `CHALLENGE`.
- [x] T062 [US3] Test: `BrowserCapture.effective_url` divergente da `source_url` esperada é incluído como sinal não-autoritativo em `evidence`/log de progresso, mas nunca decide `ACCEPTED`/`REJECTED` por si só, em `tests/unit/test_challenge_url_diagnostic_signal.py` — refs: FR-015, contracts/browser-transport-contract.md §4 ; depende de: T055 ; conclusão: um caso onde a URL diverge mas a estrutura é válida ainda resulta em `ACCEPTED` (o sinal é só diagnóstico).
- [x] T063 [US3] Implementar o sinal diagnóstico não-autoritativo de URL (T062) no laço de pausa — refs: mesmas de T062 ; depende de: T055, T062 ; conclusão: T062 passa.

**Checkpoint**: nenhuma unidade é marcada `ACCEPTED`/`VALID` enquanto challenge persiste; retomada é automática e sempre validada pelo pipeline real; nenhum bypass, nenhuma verificação paralela de "resolvido" fora de `classify_capture()`.

---

## Phase 7 — Dry-run somente-leitura (DEC-009) [US5]

**Propósito**: `orchestration/dry_run.py::plan_operation()` — mutação estruturalmente impossível (não apenas evitada por convenção).

- [x] T064 [P] [US5] Test: `ReadOnlyRepos` não expõe nenhum atributo de escrita — verificado por introspecção dos campos do dataclass (nenhum nome como `save_*`/`upsert_*`/`insert_*`) e por `mypy --strict` recusando uma tentativa deliberada de chamar uma função de escrita dentro de `plan_operation()`, em `tests/unit/test_dry_run_zero_mutation.py` — refs: contracts/orchestration-contract.md §3, SC-014 ; conclusão: teste de introspecção + nota de que uma segunda verificação estática (mypy) é exigida na Fase 13.
- [x] T065 [P] [US5] Test: `plan_operation()` reproduz a mesma decisão de `select_run()` (0/1/2+ candidatos, `--resume` inválido) apenas como texto em `OperationalPlan.run_decision`, sem levantar exceção e sem gravar nada, em `tests/unit/test_dry_run_run_decision.py` — refs: contracts/orchestration-contract.md §3, DEC-009 ; depende de: T039 ; conclusão: os 5 ramos de `select_run()` (novo/auto-resume/ambíguo/resume válido/resume inválido) aparecem refletidos em `run_decision`.
- [x] T066 [P] [US5] Test: `plan_operation()` — `specs_to_process`/`already_valid_specs`/`pending_groups_by_spec`/`specs_without_manifest_yet` refletem exatamente o estado persistido (specs descobertas, `CurrentSpecState`, manifestos, `get_pending_groups`), aplicando `--spec`/`--limit-specs`/`--limit-groups`/`--force` da mesma forma que a execução real aplicaria, em `tests/unit/test_dry_run_plan_contents.py` — refs: data-model.md §6, DEC-009 ; conclusão: um estado persistido fixo produz um `OperationalPlan` determinístico e correto nos 4 campos.
- [x] T067 [US5] Implementar `ReadOnlyRepos`, `OperationalPlan`, `plan_operation()` em `src/amayama_scraper/orchestration/dry_run.py` — refs: contracts/orchestration-contract.md §3 ; depende de: T029, T039, T064, T065, T066 ; conclusão: T064–T066 passam.
- [x] T068 [US5] Test de integração: `plan_operation()` contra SQLite real pré-populado (specs, manifesto parcial, checkpoint parcial, um run incompleto) — captura hash/dump do banco e do filesystem de raw antes e depois da chamada, assert de igualdade byte-a-byte, em `tests/integration/test_dry_run_zero_diff_sqlite.py` — refs: SC-014 ; depende de: T027, T029, T067 ; conclusão: nenhuma diferença observável antes/depois.
- [x] T069 [US5] Test: chamar `plan_operation()` nunca instancia `BrowserTransport`/`ChromeCdpTransport` — verificado por um contador de instanciação no ponto de composição (a função nem recebe um transporte como parâmetro), em `tests/unit/test_dry_run_never_touches_transport.py` — refs: spec.md DEC-009 ("zero navegação") ; depende de: T067 ; conclusão: a assinatura de `plan_operation()` não aceita `BrowserTransport` como argumento (verificação estrutural, não apenas comportamental).
- [x] T070 [US5] Test: dry-run sobre estado vazio (nenhuma spec descoberta) produz um `OperationalPlan` coerente ("nada a fazer sem descoberta real"), sem inventar specs, em `tests/unit/test_dry_run_empty_state.py` — refs: spec.md Edge Cases ; depende de: T067 ; conclusão: `discovered_spec_count == 0` e listas vazias, sem erro.
- [x] T071 [US5] Test: dry-run combinado com `--retry-rejected`/`--force` apenas relata o efeito esperado (quais unidades entrariam na passada), nunca os aplica, em `tests/unit/test_dry_run_with_retry_and_force_flags.py` — refs: contracts/orchestration-contract.md §4 ; depende de: T049, T067 ; conclusão: nenhum `CheckpointEntry` muda de estado como resultado do teste.

**Checkpoint**: `--dry-run` é comprovadamente somente-leitura por construção de tipo, não apenas por teste comportamental; reflete a mesma decisão de resume/filtros que uma execução real tomaria.

---

## Phase 8 — Collection driver (laço de descoberta-e-ação) [US1] [US2]

**Propósito**: `orchestration/collection_driver.py` — MARKET_INDEX → specs descobertas → SPEC_NAVIGATION → grupos pendentes → GROUP_DETAIL → finalização, consumindo exclusivamente primitivas já existentes de `001` mais as novas de Fases 1–7.

- [x] T072 [P] [US1] Test: `to_raw_capture_input(capture, capture_kind, run_id, ...)` — converte `BrowserCapture` em `RawCaptureInput` preservando `page_source`/`effective_url`/`captured_at` sem transformação, com `acquisition_mode=AUTOMATED_BROWSER_CDP`, em `tests/unit/test_browser_transport_to_process_capture.py` — refs: data-model.md §1, FR-005 ; conclusão: byte-a-byte de `raw_content` idêntico a `page_source.encode("utf-8")`.
- [x] T073 [US1] Implementar `to_raw_capture_input()` em `src/amayama_scraper/orchestration/collection_driver.py` — refs: mesmas de T072 ; depende de: T004, T025, T072 ; conclusão: T072 passa.
- [x] T074 [P] [US1] Test: laço de nível A (`MARKET_INDEX`) — captura via `FakeBrowserTransport`, roteia por `process_capture()` real, resultado lido de volta via `list_all_spec_identities()` reflete exatamente a fixture usada (reaproveitando `tests/fixtures/market_index/*.html` de `001`), em `tests/integration/test_collection_driver_market_index.py` — refs: FR-006, FR-009, US1 cenário 1 ; depende de: T029, T073 ; conclusão: nenhuma lista de spec entries hardcoded em `src/`.
- [x] T075 [US1] Implementar o passo de nível A dentro do driver — refs: mesmas de T074 ; depende de: T074 ; conclusão: T074 passa.
- [x] T076 [P] [US1] Test: aplicação de filtros operacionais (`--spec`, `--limit-specs`) sobre o resultado de `list_all_spec_identities()`, nunca alterando a descoberta em si, em `tests/unit/test_operational_filters.py` — refs: FR-023, FR-025, FR-009 ; conclusão: filtro por `--spec` inexistente entre as descobertas produz lista vazia, nunca erro nem invenção.
- [x] T077 [US1] Implementar `apply_operational_filters()` (specs) em `src/amayama_scraper/orchestration/collection_driver.py` — refs: mesmas de T076 ; depende de: T076 ; conclusão: T076 passa.
- [x] T078 [P] [US1][US4] Test: skip de spec já `VALID`/`STALE` (via `get_current_state()` real) a menos que esteja em `--force`, em `tests/integration/test_resume_skips_accepted_and_valid.py` — refs: FR-018, SC-004 ; depende de: T077 ; conclusão: nenhuma captura `SPEC_NAVIGATION`/`GROUP_DETAIL` é emitida para uma spec já `VALID` sem `--force`.
- [x] T079 [US1] Implementar a checagem de skip por `CurrentSpecState`/`--force` no driver — refs: mesmas de T078 ; depende de: T078 ; conclusão: T078 passa.
- [x] T080 [P] [US2] Test: laço de nível B (`SPEC_NAVIGATION`) — só executa quando `get_authoritative()` ainda é `None` para `(spec_key, run_id)`; captura via fake, roteia por `process_capture()`, manifesto real persistido (reaproveitando fixtures `tests/fixtures/spec_navigation/*.html` de `001`), em `tests/integration/test_collection_driver_spec_navigation.py` — refs: FR-007, US2 cenário 1 ; depende de: T079 ; conclusão: uma segunda passada não recaptura `SPEC_NAVIGATION` quando o manifesto já existe.
- [x] T081 [US2] Implementar o passo de nível B dentro do driver — refs: mesmas de T080 ; depende de: T080 ; conclusão: T080 passa.
- [x] T082 [P] [US2] Test: laço de nível C (`GROUP_DETAIL`) — itera `get_pending_groups()` real, resolve `source_url` via o manifesto (`ManifestGroupRef.source_url`), classifica cada unidade (`classify_pending_unit`) antes de decidir capturar, chama `process_capture(..., category_slug=..., group_id=..., spec_key=...)` real, em `tests/integration/test_collection_driver_group_detail.py` — refs: FR-008, US2 cenário 2 ; depende de: T046, T049, T081 ; conclusão: nenhum grupo fora do manifesto é navegado; `REQUIRES_EXPLICIT_RETRY` sem `--retry-rejected` é pulado.
- [x] T083 [US2] Implementar o passo de nível C dentro do driver — refs: mesmas de T082 ; depende de: T082 ; conclusão: T082 passa.
- [x] T084 [P] [US2] Test: `try_finalize_spec_entry()` real é chamado após cada `GROUP_DETAIL` aceito (mesmo acoplamento de `run_collection()`), e um `SpecSnapshot` `VALID` é produzido quando o manifesto está 100% `ACCEPTED`, em `tests/integration/test_collection_driver_end_to_end_fake.py` — refs: FR-016, US2 cenário 3, SC-002 ; depende de: T083 ; conclusão: usa exclusivamente fixtures reais de `001` (nenhuma fixture nova de domínio) via `FakeBrowserTransport`.
- [x] T085 [US2] Implementar a chamada de finalização dentro do driver — refs: mesmas de T084 ; depende de: T084 ; conclusão: T084 passa; ponta a ponta MARKET_INDEX→...→`SpecSnapshot VALID` funciona inteiramente com o fake.

**Checkpoint**: o driver dinâmico existe, reutiliza `process_capture()`/`get_pending_groups()`/`try_finalize_spec_entry()` sem modificação, e uma spec inteira alcança `VALID` usando somente o `FakeBrowserTransport` + fixtures já existentes de `001`.

---

## Phase 9 — Controles de escopo (limites, filtro, force, sem TTL) [US5]

**Propósito**: completar os filtros operacionais além do que a Fase 8 já cobriu para specs — limite de grupos, `--force` com preservação de histórico, e a confirmação de que nenhuma política de expiração por tempo existe.

- [x] T086 [P] [US5] Test: `apply_group_limit(pending, limit)` — trunca a lista de `(category_slug, group_id)` pendentes sem reordenar nem descartar de forma não-determinística, em `tests/unit/test_operational_filters.py` (extensão) — refs: FR-024 ; conclusão: mesma entrada produz sempre o mesmo subconjunto truncado.
- [x] T087 [US5] Implementar `apply_group_limit()` em `collection_driver.py` — refs: mesmas de T086 ; depende de: T083, T086 ; conclusão: T086 passa.
- [x] T088 [P] [US5][US4] Test: `--force <stable_key>` faz o driver **não** aplicar o skip de "já VALID" para essa spec — uma nova captura ocorre, um novo `SpecSnapshot` é criado, e o `SpecSnapshot` `VALID` anterior transiciona para `SUPERSEDED` (comportamento já existente de `001`, não modificado), em `tests/integration/test_force_recollection.py` — refs: FR-018, DEC-008, spec.md FR-032a ; depende de: T079 ; conclusão: o `RawCapture`/`RawBlob` da coleta anterior permanece intacto e consultável (nenhuma escrita anterior é apagada).
- [x] T089 [US5] Implementar o bypass de `--force` no driver (reaproveitando T079) — refs: mesmas de T088 ; depende de: T088 ; conclusão: T088 passa.
- [x] T090 [P] [US5] Test negativo: nenhuma função do driver/planejador consulta `datetime.now()`/timestamps para decidir se uma spec `VALID` está "stale" — auditoria de código (busca por comparação de datas fora de `snapshots/`) confirmando ausência de TTL, em `tests/unit/test_no_time_based_staleness.py` — refs: DEC-008 ; conclusão: nenhuma spec `VALID` é recoletada apenas por decorrer tempo, em nenhum teste da suíte.
- [x] T091 [P] [US5] Test: filtro por `--spec` aceita múltiplos valores (repetível), cada um validado contra `list_all_spec_identities()` — um valor não descoberto é reportado como erro de uso claro, nunca silenciosamente ignorado nem inventado, em `tests/unit/test_operational_filters.py` (extensão) — refs: FR-025, FR-009 ; conclusão: erro explícito para `stable_key` desconhecido.
- [x] T092 [US5] Implementar a validação de `--spec` (T091) — refs: mesmas de T091 ; depende de: T077, T091 ; conclusão: T091 passa.
- [x] T093 [US5] Test de integração: combinação `--limit-specs N` + `--limit-groups M` + `--spec X` sobre um estado com múltiplas specs/grupos descobertos via fake, confirmando que exatamente os limites/filtro pedidos são respeitados simultaneamente, em `tests/integration/test_operational_filters_combined.py` — refs: US5 cenário, quickstart.md ; depende de: T087, T092 ; conclusão: contagem exata de specs/grupos processados bate com os parâmetros.

**Checkpoint**: todos os controles de escopo descritos em `spec.md` (User Story 5) funcionam de forma composável e determinística; `--force` nunca apaga histórico; nenhuma forma de TTL automático existe em nenhum caminho de código.

---

## Phase 10 — CLI

**Propósito**: `cli/main.py`/`cli/options.py` — interface fina, sem lógica de domínio, `argparse` da stdlib.

- [x] T094 [P] Criar pacote `src/amayama_scraper/cli/__init__.py` (vazio) — refs: plan.md "Project Structure" ; conclusão: pacote importável.
- [x] T095 [P] Test: parsing de argumentos — todas as flags de contracts/orchestration-contract.md §4 são aceitas com os tipos corretos; `--resume`/`--new-run` são mutuamente exclusivos (erro de uso antes de qualquer lógica de orquestração); `--spec`/`--force` são repetíveis, em `tests/unit/test_cli_options.py` — refs: contracts/orchestration-contract.md §4 ; conclusão: cada flag tem ao menos um caso de teste positivo; a exclusividade mútua é testada.
- [x] T096 Implementar `cli/options.py` (definição `argparse`) — refs: mesmas de T095 ; depende de: T094, T095 ; conclusão: T095 passa.
- [x] T097 [P] Test: composição do CLI (`cli/main.py`) — é o **único** ponto que instancia `ChromeCdpTransport` concreto (verificado por busca estática/mock de importação), nunca instanciado dentro de `orchestration/`, em `tests/unit/test_cli_composition_root.py` — refs: research.md §5, Constitution §6 ; conclusão: teste falha se `orchestration/collection_driver.py` importar `chrome_cdp_adapter` diretamente.
- [x] T098 Implementar `cli/main.py` — resolve config (CDP host/port, db-path, raw-root), instancia adapters concretos (`ChromeCdpTransport`, `FilesystemRawBlobStore`, `SqliteRawCaptureRepository`, conexão `db.connect()`), chama `select_run()`/`plan_operation()`/`collection_driver` conforme as flags — refs: contracts/orchestration-contract.md §4, plan.md "CLI planejada" ; depende de: T017, T027, T029, T039, T067, T085, T096, T097 ; conclusão: T097 passa; nenhuma lógica de domínio é reimplementada em `cli/main.py` (apenas composição).
- [x] T099 [P] Test: `amayama-scraper run --dry-run` (via `cli/main.py`, transporte nunca instanciado) produz saída do plano no stdout sem tocar SQLite/filesystem além de leitura, em `tests/integration/test_cli_dry_run_end_to_end.py` — refs: DEC-009, SC-014 ; depende de: T098 ; conclusão: mesmo teste de zero-diff da Fase 7, agora através do CLI completo.
- [x] T100 [P] Test: erro de uso claro para `--resume` + `--new-run` simultâneos, e para `--resume <run_id inexistente>`, sem stack trace bruto exposto ao operador, em `tests/unit/test_cli_error_messages.py` — refs: contracts/orchestration-contract.md §4 ; depende de: T096 ; conclusão: mensagens objetivas, código de saída não-zero.
- [x] T101 Test de integração: `amayama-scraper run --limit-specs 1 --limit-groups 2` ponta a ponta via CLI com `ChromeCdpTransport` substituído por `FakeBrowserTransport` (injeção de dependência no ponto de composição, exclusivamente para este teste), confirmando que exatamente 1 spec e até 2 grupos são processados e persistidos, em `tests/integration/test_cli_limited_run_end_to_end.py` — refs: US5, quickstart.md ; depende de: T085, T093, T098 ; conclusão: estado final do SQLite reflete os limites pedidos.

**Checkpoint**: CLI compõe todos os adapters concretos em um único ponto, nunca vaza `selenium`/`sqlite3` para `orchestration/`, e os fluxos principais (`--dry-run`, execução limitada) funcionam ponta a ponta com um transporte substituível.

---

## Phase 11 — Observabilidade

**Propósito**: `orchestration/progress_reporter.py` — reuso estrito de `log_event()` já existente, sem novo framework de logging.

- [x] T102 [P] Test: `progress_reporter` emite um evento por marco (`RUN_STARTED`, `SPEC_STARTED`, `GROUP_ACCEPTED`, `GROUP_SKIPPED_CHECKPOINT`, `CHALLENGE_WAITING`, `RETRY_TRANSPORT`, `GROUP_REJECTED`, `SPEC_COMPLETE`, `RUN_SUMMARY`) via `log_event()` real, correlacionado por `run_id`, em `tests/unit/test_progress_reporter.py` — refs: FR-027, research.md §15 ; conclusão: cada marco produz exatamente uma linha JSON com `event` correto.
- [x] T103 Implementar `progress_reporter.py` — refs: mesmas de T102 ; depende de: T102 ; conclusão: T102 passa.
- [x] T104 [P] Test: `progress_reporter` nunca recebe/passa `page_source`/HTML bruto para `log_event()` — reaproveita a proteção já existente (`RawContentInLogError`) e adiciona um teste específico do reportador confirmando que ele nunca tenta passar esse campo, em `tests/unit/test_progress_reporter.py` (caso adicional) — refs: Constitution §4 (auditoria sem vazamento) ; depende de: T103 ; conclusão: nenhuma chamada de `progress_reporter` inclui `page_source`/`raw_content`/`html`.
- [x] T105 [P] Test: contador de resumo final (`RUN_SUMMARY`) agrega corretamente ACCEPTED/SKIPPED/CHALLENGE/RETRY_TRANSPORT/REJECTED ao longo de uma execução simulada, em `tests/unit/test_progress_reporter.py` (caso adicional) — refs: FR-027 ; depende de: T103 ; conclusão: contagens batem com os eventos emitidos.
- [x] T106 Integrar `progress_reporter` nos pontos relevantes de `collection_driver.py` (sem duplicar lógica de decisão — apenas reportar o que já foi decidido) — refs: FR-027 ; depende de: T085, T103 ; conclusão: rodar o teste ponta a ponta da Fase 8 (T084) com um `emit` capturando linhas produz a sequência esperada de eventos.
- [x] T107 Test de integração: saída de terminal de uma execução completa (via T101, capturando stdout) contém spec atual, grupo atual, progresso atual/total, e resumo final — em `tests/integration/test_cli_limited_run_end_to_end.py` (extensão de T101) — refs: FR-027, User Story 5 cenário 6 ; depende de: T101, T106 ; conclusão: todos os campos exigidos por FR-027 aparecem na saída capturada.

**Checkpoint**: observabilidade cobre exatamente os marcos exigidos por `spec.md`, sem introduzir dependência de logging nova e sem risco de vazamento de HTML bruto.

---

## Phase 12 — Testes offline integrados (ponta a ponta, sem rede)

**Propósito**: fechar lacunas de cobertura ponta a ponta que nenhuma fase anterior isoladamente garante — todas usando `FakeBrowserTransport` e fixtures já existentes.

- [x] T108 [P] Test: execução completa — `MARKET_INDEX` → N specs descobertas → cada uma completa até `SpecSnapshot VALID`, tudo via fake, reaproveitando os 7 manifests/fixtures reais de `001` (`tests/fixtures/regression/`), em `tests/integration/test_collection_driver_multi_spec_fake.py` — refs: SC-009, US2 ; depende de: T085 ; conclusão: a mesma arquitetura percorre múltiplas specs sem alteração de código entre uma e outra.
- [x] T109 [P] Test: segunda execução (novo processo simulado, mesmo `run_id` via `--resume`) sobre o estado produzido por T108 não recaptura nenhuma unidade `ACCEPTED`/spec `VALID`, em `tests/integration/test_second_run_no_recollection.py` — refs: FR-018, SC-003, SC-004, spec.md MVP item 11 ; depende de: T041, T108 ; conclusão: zero chamadas de `transport.navigate()` observadas para unidades já concluídas.
- [x] T110 [P] Test: run ambíguo — duas execuções incompletas do mesmo escopo, terceira invocação sem `--resume`/`--new-run` falha antes de qualquer navegação, em `tests/integration/test_ambiguous_run_blocks_navigation.py` — refs: DEC-005, SC-010 ; depende de: T039 ; conclusão: `FakeBrowserTransport.navigate()` nunca é chamado nesse teste.
- [x] T111 [P] Test: `--new-run` sobre estado com incompleta compatível — nova execução, incompleta anterior permanece intocada e retomável depois, em `tests/integration/test_new_run_preserves_previous.py` — refs: DEC-005 ; depende de: T039 ; conclusão: um `--resume` subsequente para o `run_id` antigo ainda funciona normalmente.
- [x] T112 [P] Test: rejeição sem retry — unidade `INVALID` via fixture real permanece `REJECTED` através de 3 passadas do driver sem `--retry-rejected`, e é retentada somente na passada com a flag, em `tests/integration/test_no_auto_retry_on_validation_rejection.py` — refs: FR-020, SC-011 ; depende de: T083 ; conclusão: exatamente 1 tentativa de navegação nas 3 primeiras passadas, +1 na passada com retry manual.
- [x] T113 [P] Test: retry de transporte — `FakeBrowserTransport` falha 2 vezes e sucede na 3ª dentro do limite configurado, unidade acaba `ACCEPTED` na mesma passada, em `tests/integration/test_transport_retry_recovers.py` — refs: research.md §10 ; depende de: T023, T083 ; conclusão: `attempt_count` reflete as tentativas internas + a final.
- [x] T114 [P] Test: skip de `ACCEPTED` dentro da mesma spec — grupo já aceito não é renavegado mesmo com outros grupos ainda pendentes na mesma passada, em `tests/integration/test_resume_skips_accepted_and_valid.py` (caso adicional) — refs: SC-003 ; depende de: T083 ; conclusão: contagem de navegações == contagem de grupos pendentes, nunca inclui os já aceitos.
- [x] T115 [P] Test: ausência de hardcode — busca estática (`grep`/AST) por `2HBC3X`/`S1BC3X`/`S6BC74`/`S7BC74`/`S7BC8A`/`AGDC8A` em todo `src/amayama_scraper/`, em `tests/regression/test_market_index_discovery_no_hardcode.py` — refs: FR-009, SC-008 ; conclusão: busca retorna vazio; os mesmos valores podem aparecer livremente em `tests/`/`docs/`.
- [x] T116 [P] Test: fronteira final de Selenium — reexecução consolidada dos testes de T011 mais um caso adicional: `orchestration/collection_driver.py`, `orchestration/run_selection.py`, `orchestration/retry_classification.py`, `orchestration/dry_run.py` também não importam `selenium` (só `cli/main.py` compõe o adapter concreto), em `tests/unit/test_orchestration_no_duplicated_logic.py` (extensão — novo teste parametrizado sobre os arquivos novos de `orchestration/`) — refs: research.md §5, §13 ; depende de: T012, T039, T046, T055, T067, T085 ; conclusão: `pipeline.py` continua coberto pelo teste original (T012 não o duplica), e os novos arquivos passam a ser cobertos também.
- [x] T117 [P] Test: `SpecSnapshot` final — uma spec coletada inteiramente via fake atinge `state == VALID` usando `compute_collection_complete()`/`finalize_spec_entry()` sem nenhuma alteração de comportamento em relação a `001` (mesmo teste de paridade que os testes de `001` já validam, agora disparado pelo driver novo), em `tests/integration/test_collection_driver_end_to_end_fake.py` (caso adicional) — refs: SC-002, spec.md MVP item 12 ; depende de: T085 ; conclusão: `SpecSnapshot.collection_complete is True` e `state == VALID`.
- [x] T118 [P] Test: challenge com múltiplas unidades pendentes simultaneamente (uma spec com challenge em um grupo enquanto outra spec já está `VALID`) — confirma que o laço bloqueante não corrompe nem mistura o progresso entre specs distintas, em `tests/integration/test_challenge_does_not_affect_other_specs.py` — refs: US3 cenário 3, FR-028 (sequencial) ; depende de: T055, T085 ; conclusão: a spec já `VALID` permanece `VALID` e não é revisitada por causa do challenge em outra spec.
- [x] T119 [P] Test: `--force` não apaga `RawBlob`/`RawCapture` da coleta anterior — reconstrução via `reconstruct_raw_content()` (já existente) continua funcionando para o `capture_id` antigo após uma recoleta forçada, em `tests/integration/test_force_recollection.py` (caso adicional) — refs: FR-032a, Constitution §4 ; depende de: T089 ; conclusão: os dois `RawCapture` (antigo e novo) coexistem e são individualmente recuperáveis.
- [x] T120 Test de regressão: reexecutar (sem modificação) a suíte de regressão já existente de `001` (pares `2HBC3X`↔`S1BC3X` etc.) para confirmar que nada nesta feature alterou `parts_relation == EXACT`/identidade/fingerprints — refs: Constitution §12, spec.md "Decisões herdadas" ; depende de: T085 ; conclusão: `pytest tests/regression/` (suíte de `001`) permanece 100% verde sem nenhuma alteração de arquivo.
- [x] T121 Consolidar: revisar todos os `TODO`/`xfail`/skip introduzidos ao longo das Fases 1–12 (não deve haver nenhum) — refs: Constitution §12 ; depende de: T001–T120 ; conclusão: `grep -rn "TODO\|xfail\|pytest.mark.skip" src/ tests/` restrito ao que já existia em `001` (nenhuma adição desta feature).

**Checkpoint**: comportamento ponta a ponta (descoberta, coleta, resume, retry, challenge, dry-run, force, limites, ausência de hardcode, fronteira Selenium) está provado 100% offline, sem depender da Amayama.

---

## Phase 13 — Quality gates

**Propósito**: os mesmos portões de qualidade já exigidos por `001`, aplicados ao código desta feature.

- [x] T122 Rodar suíte completa (`pytest`) e confirmar 100% verde, incluindo toda a suíte de `001` inalterada — refs: Constitution §12 ; depende de: T001–T121 ; conclusão: `pytest` retorna 0 falhas.
- [x] T123 Rodar cobertura (`pytest --cov`) e confirmar `>= 90%` sobre `src/amayama_scraper` (incluindo os novos pacotes `transport/`, `cli/`, e os novos módulos de `orchestration/`) — refs: pyproject.toml `fail_under = 90` ; depende de: T122 ; conclusão: relatório de cobertura `>= 90%` sem exclusões ad hoc não justificadas.
- [x] T124 Rodar `ruff check` sobre `src/`/`tests/` e corrigir achados — refs: pyproject.toml `[tool.ruff]` ; depende de: T122 ; conclusão: zero achados.
- [x] T125 Rodar `ruff format --check` — refs: mesmas de T124 ; depende de: T124 ; conclusão: zero diffs de formatação.
- [x] T126 Rodar `mypy --strict` sobre `src/amayama_scraper` (incluindo `transport/`, `cli/`, novos módulos de `orchestration/`) — refs: mypy.ini ; depende de: T122 ; conclusão: zero erros, incluindo a verificação estática de T064 (dry-run estruturalmente incapaz de escrever).
- [x] T127 Reexecutar especificamente os testes de fronteira de arquitetura (T011, T012, T013, T097, T116) como um grupo nomeado e confirmar 100% verdes — refs: research.md §13 ; depende de: T126 ; conclusão: nenhum teste de fronteira foi enfraquecido ou removido, apenas escopo ajustado conforme T011/T012.
- [x] T128 Auditoria final de hardcode — reexecutar T115 mais uma varredura manual de `git diff` desta feature contra `main`/branch base, confirmando que nenhum dos 6 códigos de catálogo (mais nenhum outro `catalog_id` específico) aparece fora de `tests/`/`docs/`/`specs/` — refs: FR-009, SC-008 ; depende de: T115 ; conclusão: `git diff` revisado linha a linha para esse padrão.
- [x] T129 Auditoria final de segurança — busca textual por termos proibidos (`captcha`, `solver`, `bypass`, `stealth`, `undetected`, `proxy`, `fingerprint spoof`, `cookie` combinado com "bypass"/"token") em todo `src/` desta feature, reaproveitando o padrão de `tests/unit/test_no_bypass_forbidden_terms.py` de `001` (estendido para cobrir `transport/`/`cli/`/novos `orchestration/`) — refs: Constitution §5, spec.md "Segurança arquitetural" ; depende de: T128 ; conclusão: zero ocorrências fora de comentários que **proíbem** explicitamente esses termos (como este próprio arquivo).
- [x] T130 Rodar `quickstart.md` cenários 0–9 (offline) como suíte nomeada e confirmar que cada comando de exemplo corresponde a um teste real existente (nenhum cenário do quickstart ficou órfão de teste) — refs: quickstart.md ; depende de: T129 ; conclusão: os 10 cenários (0–9) têm cada um pelo menos um teste automatizado correspondente já criado nas Fases 1–12.

**Checkpoint**: suíte verde, cobertura ≥90%, Ruff e mypy strict limpos, nenhum hardcode, nenhum termo de bypass/evasão em código de produção.

---

## Phase 14 — Validação real controlada (evidência manual, fora de CI)

**Propósito**: confirmar contra a Amayama real que o que foi provado offline também funciona ao vivo. **Nunca executada em CI**; não requer provocar/fabricar CAPTCHA.

**Status: PENDENTE DE EVIDÊNCIA MANUAL.** T131–T137 exigem interação direta do operador (um Chrome real aberto pelo próprio operador, acesso real à Amayama, e — na Fase D — uma interrupção manual via Ctrl+C) que não pode ser concluída automaticamente com segurança nem simulada como se fosse real. Nenhuma evidência foi simulada ou marcada como concluída sem execução real. Procedimento exato para o operador executar (usando o CLI já implementado, `python -m amayama_scraper.cli.main` ou um entrypoint equivalente configurado em `pyproject.toml`):

1. Abrir um Chrome real com depuração remota habilitada e sem tradução automática ativa (`quickstart.md` "Pré-requisitos"): `google-chrome --remote-debugging-port=9222 --user-data-dir=/tmp/amayama-chrome-profile`.
2. Fase A: `amayama-scraper run --dry-run` (confirma attach/plano sem navegar) seguido de `amayama-scraper run --limit-specs 0` (só MARKET_INDEX) — confirmar via terminal que specs reais do Amarok `AMA BR` foram descobertas.
3. Fase B: `amayama-scraper run --spec <STABLE_KEY> --limit-groups 2` sobre uma spec real descoberta na Fase A.
4. Fase C: `amayama-scraper run --spec <STABLE_KEY>` (sem limite) até `SpecSnapshot VALID`.
5. Fase D: repetir a Fase C, mas interromper com Ctrl+C no meio; depois `amayama-scraper run --resume <run_id>` e confirmar (via log JSON) que grupos já `ACCEPTED` não são renavegados.
6. Fase F: rodar novamente `amayama-scraper run --spec <STABLE_KEY>` sobre a spec já `VALID` e confirmar `SPEC_SKIPPED_ALREADY_VALID` sem nenhuma navegação adicional.
7. Fase G: executada apenas se um challenge real ocorrer organicamente durante 2–6; não deve ser provocada deliberadamente.

Nenhuma das tasks abaixo foi marcada concluída — permanecem `[ ]` até que o Product Owner (ou quem ele designar) execute o procedimento acima e anexe a evidência real.

- [ ] T131 Fase A — Attach a um Chrome real (iniciado pelo operador conforme `quickstart.md` "Pré-requisitos") + captura real de `MARKET_INDEX` do Amarok `AMA BR` via `amayama-scraper run --dry-run` seguido de uma execução mínima — refs: quickstart.md "Fase A" ; depende de: T098 ; conclusão: evidência (log/output) anexada ao PR mostrando ao menos 1 spec entry real descoberta, sem nenhum hardcode envolvido.
- [ ] T132 Fase B — Uma spec real descoberta, manifesto real, `--limit-groups` pequeno — refs: quickstart.md "Fase B" ; depende de: T131 ; conclusão: evidência mostrando manifesto real persistido e grupos limitados `ACCEPTED`.
- [ ] T133 Fase C — Mesma spec completa até `SpecSnapshot VALID` real — refs: quickstart.md "Fase C" ; depende de: T132 ; conclusão: evidência de `state == VALID` com `collection_complete == True` sobre dados reais.
- [ ] T134 Fase D — Interrupção (Ctrl+C) no meio da coleta + `--resume <run_id>` — refs: quickstart.md "Fase D" ; depende de: T133 ; conclusão: evidência de que grupos já `ACCEPTED` antes da interrupção não são renavegados (logs comparados).
- [ ] T135 Fase F (segunda execução) — nova invocação sobre o mesmo escopo já `VALID`, sem `--force` — refs: spec.md MVP item 11 ; depende de: T134 ; conclusão: evidência de que nenhuma recoleta desnecessária ocorre.
- [ ] T136 Fase G — Challenge real, **somente se ocorrer organicamente** durante A–F — refs: quickstart.md "Fase E" ; depende de: T131 ; conclusão: se ocorrer, evidência de pausa + instrução objetiva + retomada automática após resolução manual; se não ocorrer, registrar explicitamente "não observado nesta rodada" — não é bloqueante, pois a prova automatizada (Fase 6, offline) já cobre o comportamento.
- [ ] T137 Consolidar evidência de validação real (T131–T136) em um documento/anexo de evidência (ex.: `specs/002-amarok-ama-br-browser-scraper/evidence/` ou local acordado com o PO) — refs: spec.md FR-036 ("evidência de integração, nunca substituto da suíte automatizada") ; depende de: T131–T136 ; conclusão: evidência anexada e referenciada no PR; deixado explícito que essa evidência não substitui T122–T130.

**Checkpoint**: MVP demonstrado de ponta a ponta contra o site real, nos termos exatos do Issue #10 — sem provocar CAPTCHA deliberadamente.

---

## Dependências e ordem de execução

### Dependências entre fases

- **Fase 1** não depende de nada — pode começar imediatamente.
- **Fase 2** depende da Fase 1 (T004, T006, T008 — tipos/erros do port).
- **Fase 3** é independente de Fases 1–2 (toca apenas `persistence/`/`ingestion/capture_kind.py`) — pode rodar em paralelo com elas por um time diferente, mas T025 (enum) é consumida por T072/T073 (Fase 8).
- **Fase 4** depende da Fase 3 (T027 — `list_incomplete_runs`).
- **Fase 5** depende da Fase 3 (T027 indiretamente via checkpoint) — na prática, independente das Fases 1–2/4; pode rodar em paralelo com a Fase 4.
- **Fase 6** depende das Fases 1 (fake/port), 3 (checkpoint) e 5 (`classify_pending_unit`).
- **Fase 7** depende das Fases 3 (`list_all_spec_identities`) e 4 (`select_run`).
- **Fase 8** depende de **todas** as Fases 1–6 (é o ponto de integração de transporte + run selection + retry + challenge).
- **Fase 9** depende da Fase 8.
- **Fase 10 (CLI)** depende das Fases 2, 4, 7, 8, 9.
- **Fase 11** depende da Fase 8 (e opcionalmente 10 para o teste ponta a ponta de stdout).
- **Fase 12** depende de todas as Fases 1–11 completas.
- **Fase 13** depende da Fase 12.
- **Fase 14** depende da Fase 13 (só faz sentido validar ao vivo depois que tudo passa offline).

### Sequência crítica (caminho mais longo)

Fase 1 → Fase 2 → Fase 6 → Fase 8 → Fase 9 → Fase 10 → Fase 11 → Fase 12 → Fase 13 → Fase 14.
(Fases 3, 4, 5, 7 podem ser paralelizadas entre si e com parte da Fase 2, desde que a Fase 8 só comece depois que todas — 1 a 6 — estejam prontas.)

### Oportunidades de paralelização

- Dentro de cada fase, toda task marcada `[P]` é paralelizável com as demais `[P]` da mesma fase (arquivos distintos, sem dependência entre si).
- **Entre fases**: Fase 3 pode rodar inteiramente em paralelo com Fases 1–2 (times/sessões diferentes) — nenhuma depende da outra até a Fase 8. Fase 5 pode rodar em paralelo com a Fase 4 (ambas dependem apenas da Fase 3). Fase 7 pode começar assim que Fases 3 e 4 estiverem prontas, em paralelo com as Fases 5/6.
- Fases 12, 13 e 14 são estritamente sequenciais entre si e em relação a tudo antes delas (integração → qualidade → validação real).

---

## Rastreabilidade — FR/DEC/SC/User Story → Tasks

| Requisito/Decisão | Tasks |
|---|---|
| FR-001, FR-002 (transporte via Chrome real, Selenium/CDP) | T001–T023 |
| FR-003, FR-003a (attach CDP, transporte atrás de porta) | T004, T006, T015–T021, T097 |
| FR-004 (sem tradução automática) | quickstart.md pré-requisitos (pré-condição operacional, sem task de código — nenhuma automação é criada para isso, conforme research.md §11) |
| FR-005 (campos de RawCaptureInput preenchidos do transporte real) | T003, T004, T072, T073 |
| FR-006, FR-009 (descoberta sem hardcode) | T074, T075, T115, T128 |
| FR-007, FR-008 (SPEC_NAVIGATION, GROUP_DETAIL reais) | T080–T083 |
| FR-010 a FR-013 (challenge, sem bypass) | T052–T063, T129 |
| FR-014 a FR-016 (raw first, sem decisão paralela de outcome) | T024, T053 (implícito via reuso), T072, T073, T082 |
| FR-017 a FR-021 (checkpoint, seleção de run, retry) | T032–T051 |
| FR-018, FR-019, FR-026 (resume, DEC-005) | T033–T041, T088, T089, T109–T111 |
| FR-020, FR-021 (retry, DEC-006) | T042–T051, T112, T113 |
| FR-022 a FR-025 (dry-run, limites, filtro) | T064–T093 |
| FR-027 (observabilidade) | T102–T107 |
| FR-028 a FR-030 (rate/retry responsável) | T022, T023, T053 |
| FR-031, FR-032, FR-032a (persistência, sem migration, force) | T024–T032, T088, T089, T119 |
| FR-033 (sem otimização por equivalência) | plan.md "Integração com o core existente" (nenhuma task altera `equivalence/`; confirmado por T120) |
| FR-034 a FR-036 (testabilidade, validação real ≠ suíte) | T009, T010, todas as Fases 12–14 |
| FR-037 (qualidade) | T122–T130 |
| DEC-005 | T033–T041, T065, T110, T111 |
| DEC-006 | T042–T051, T060, T112, T113 |
| DEC-007 | T001, T011–T023, T097, T116, T127 |
| DEC-008 | T088–T090, T119 |
| DEC-009 | T064–T071, T099 |
| SC-001, SC-008 | T074, T115, T128, T131 |
| SC-002 | T084, T085, T117, T133 |
| SC-003, SC-004 | T041, T078, T109, T114, T134, T135 |
| SC-005 | T052–T063, T136 |
| SC-006 | T024 (raw preservado inclusive para automated), Constitution §4 já garantida por `001` |
| SC-007 | T122–T130 |
| SC-009 | T108 |
| SC-010 | T110 |
| SC-011 | T112 |
| SC-012 | T011–T013, T097, T116, T127 |
| SC-013 | T090, T119 |
| SC-014 | T068, T069, T099 |
| User Story 1 (P1) | T074–T077, T131 |
| User Story 2 (P2) | T080–T085, T108, T117, T132, T133 |
| User Story 3 (P3) | T046–T063, T118, T136 |
| User Story 4 (P4) | T033–T041, T078, T088, T109, T114, T134 |
| User Story 5 (P5) | T064–T093, T099–T101, T130 |
| User Story 6 (P6) | T022, T023, T053 (navegação conservadora/sequencial — confirmado por ausência de qualquer mecanismo de concorrência entre Fases 8–10) |

Nenhum FR/DEC/SC/User Story de `spec.md` ficou sem task correspondente na tabela acima.

---

Este `tasks.md` é exclusivamente de decomposição. Nenhuma task foi executada. Aguarda autorização explícita do Product Owner para iniciar `CLAUDE IMPLEMENTA` (Constitution §14, `docs/sdd/EXECUTION_POLICY.md`).
