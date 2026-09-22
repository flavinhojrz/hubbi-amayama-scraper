---
description: "Task list — feature 005 (performance worker pool)"
---

# Tasks: Performance Worker Pool — Paralelismo Controlado por Spec

**Input**: spec.md, plan.md, data-model.md, contracts/worker-pool-contract.md (todos neste diretório)

**Tests**: obrigatórios (Constitution §12, Execution Policy "Política de
testes") — toda task de regra estrutural inclui teste correspondente.

**Autorização**: PO autorizou explicitamente `CLAUDE IMPLEMENTA` (mensagem
"PO APPROVAL — Feature 005", aprovando `spec.md`/`plan.md`/`data-model.md`/
`contracts/worker-pool-contract.md`/`quickstart.md`/`tasks.md` e autorizando
a execução das tasks abaixo). Todas as tasks foram executadas nesta
conversa. Nenhuma task fez coleta real nem `git commit`/`push` (restrição
explícita do PO, reforçada pela task da Fase final).

## Fase 1: Fundação — migration + rate limiter puro (bloqueante para todas as demais)

- [x] T501 [P] Criar `src/amayama_scraper/persistence/migrations/0009_worker_pool.sql`:
      `spec_lease`, `rate_limiter_state`, `challenge_event`,
      `worker_heartbeat` (data-model.md §1–§4). Puramente aditivo — zero
      `ALTER TABLE` sobre schema existente.
- [x] T502 [P] Criar `src/amayama_scraper/orchestration/rate_limiter.py`:
      `RateLimiterConfig`, `RateLimiterState`, `on_challenge_observed()`,
      `on_stability_tick()` — funções puras, sem I/O (contracts/
      worker-pool-contract.md §4, FR-060 a FR-065).
- [x] T503 [P] `tests/unit/test_rate_limiter.py` (NOVO): decremento em 1 ao
      atingir limiar dentro da janela (nunca abaixo de 1); incremento em 1
      após período estável (nunca acima de `max_concurrency`); reinício do
      relógio de estabilidade em ambos os eventos; determinismo (mesma
      sequência de eventos → mesma sequência de estados) — SC-004.

**Checkpoint**: FR-060 a FR-065 cobertos e testáveis isoladamente, sem
tocar persistência/CLI/orquestração ainda.

---

## Fase 2: Repositórios de coordenação (I/O fino sobre a migration da Fase 1)

- [x] T504 Criar `src/amayama_scraper/persistence/repositories/lease_repo.py`:
      `try_claim()` (UPSERT condicional + leitura de confirmação, ambos numa
      única `BEGIN IMMEDIATE`, data-model.md §1), `renew_lease()`,
      `release_lease()`, `count_active_leases()` (FR-020 a FR-025, FR-031).
- [x] T505 [P] `tests/unit/test_lease_claim_semantics.py` (NOVO, conexão
      SQLite real em arquivo temporário — não é teste de domínio puro, é
      contrato de transação): duas chamadas sequenciais de `try_claim()`
      pelo mesmo `owner` renovam; por `owner` diferente após expiração
      recuperam; por `owner` diferente antes de expirar falham.
- [x] T506 [P] Criar `src/amayama_scraper/persistence/repositories/rate_limiter_repo.py`:
      `read_state()`/`write_state()` (lazy-init na primeira leitura) —
      delega toda decisão a `rate_limiter.py` (T502), nunca decide política
      aqui (Constitution §6).
- [x] T507 [P] Criar `src/amayama_scraper/persistence/repositories/challenge_event_repo.py`:
      `record_challenge_observed()`, `record_challenge_resolved()`,
      `count_in_window()` (fonte única do rate limiter e das métricas de
      challenge — data-model.md §3).
- [x] T508 [P] Criar `src/amayama_scraper/persistence/repositories/worker_heartbeat_repo.py`:
      `upsert_heartbeat()`, `count_active()` (data-model.md §4 — apenas
      observabilidade, nunca decide claim/lease).

**Checkpoint**: toda a camada de persistência de coordenação existe e é
testável isoladamente (SC-002, SC-003 no nível de repositório).

**Adição além da lista original**: `tests/unit/test_worker_pool_repos.py`
(NOVO) — cobertura direta de T506–T508 (`rate_limiter_repo`,
`challenge_event_repo`, `worker_heartbeat_repo`: lazy-init, janela de
tempo, staleness), que a lista original só cobria indiretamente via testes
de integração.

---

## Fase 3: Extração de `process_one_spec()` (sem mudança de comportamento)

- [x] T509 `orchestration/collection_driver.py`: extrair o corpo do laço
      `for spec in specs_to_process` (SPEC_NAVIGATION → `get_pending_groups`
      → GROUP_DETAIL → `try_finalize_spec_entry`) para uma função
      `process_one_spec(transport, conn, blob_store, capture_repo, *,
      run_id, context, spec, filters, poll_interval, challenge_timeout,
      min_interval, throttled_navigate, on_event)`. `run_collection_driver()`
      passa a chamar essa função dentro do mesmo laço — **nenhuma mudança de
      comportamento observável**, apenas extração mecânica.
- [x] T510 [P] Rodar a suíte de integração existente de `collection_driver`
      (`test_collection_driver_*`, `test_challenge_*`,
      `test_resume_skips_accepted_and_valid.py`,
      `test_no_auto_retry_on_validation_rejection.py`) — todas devem
      permanecer verdes sem nenhuma alteração de asserção (prova de que a
      extração é puramente mecânica, SC-001).

**Checkpoint**: `process_one_spec()` existe, é a única lógica por-spec, e é
usada pelo caminho legado sem regressão — pronta para ser reusada pela Fase
4 sob lease.

---

## Fase 4: `worker_pool.py` — orquestrador e workers (US2, US3, US6)

- [x] T511 Criar `src/amayama_scraper/orchestration/worker_pool.py`:
      `next_claimable_spec()` (checagem de `effective_concurrency` +
      `try_claim()` na mesma transação, contracts/worker-pool-contract.md
      §3, FR-062), `run_worker_loop()` (loop de claim → `process_one_spec()`
      → release, contracts §2), `run_pool()` (Nível A sequencial pelo
      orquestrador → spawn de N processos worker → loop de métricas →
      `join()` → `_maybe_mark_run_completed()` única vez, contracts §1,
      FR-033).
      **Desvio de nomenclatura do plan.md (mecânico, sem efeito semântico)**:
      o entrypoint de processo real chama-se `_worker_process_entrypoint()`
      e vive em `cli/main.py` (não `worker_main()` em `worker_pool.py`) —
      `tests/unit/test_cli_composition_root.py` exige que **somente**
      `cli/main.py` importe `transport.chrome_cdp_adapter`; como esse
      entrypoint precisa construir um `ChromeCdpTransport` real, ele não
      pode viver em `orchestration/`. `run_worker_loop()` (em
      `worker_pool.py`) recebe `transport`/`conn` já construídos e é o que
      de fato é testado — `worker_pool.py` nunca importa `selenium`/
      `chrome_cdp_adapter` (verificado pelos testes de fronteira já
      existentes). `run_pool()`/`run_worker_loop()` recebem `worker_target`/
      `process_factory` injetados (produção: `multiprocessing.get_context
      ("spawn")`, montado em `cli/main.py`) em vez de construir o pool
      internamente — mesma razão.
- [x] T512 `run_worker_loop()`/`run_pool()` chamam `_require_run_context()`
      (novo, em `worker_pool.py`) — mesma checagem já usada por
      `run_collection_driver()` (`CollectionRun.scope == context.scope()`,
      FR-100/FR-101) — nunca reconstrói/infere contexto de forma
      independente por worker. `process_one_spec()`/`process_capture()`
      continuam aplicando, independentemente, a validação `spec_key ->
      context` já existente (`_require_matching_spec_context`, 004) —
      defesa em profundidade inalterada.
- [x] T513 [P] `tests/integration/test_worker_pool_no_double_claim.py`
      (NOVO): dois `multiprocessing.Process` (ou dois workers reais via
      `worker_pool.worker_main`) competindo pelo mesmo conjunto de specs
      sobre um SQLite real em arquivo temporário — nenhuma `spec_key` é
      processada por dois workers (SC-002).
- [x] T514 [P] `tests/integration/test_worker_pool_lease_recovery.py`
      (NOVO): um "worker morto" simulado (lease criado e nunca renovado,
      `expires_at` no passado) é recuperado por outro worker sem
      reprocessar grupos já `ACCEPTED` (SC-003).
- [x] T515 [P] `tests/integration/test_worker_pool_context_isolation.py`
      (NOVO): reusa `tests/support.py::AMAROK_CONTEXT`/`GOL_CONTEXT` (004) —
      pool de workers de GOL rodando sobre banco com Amarok populada nunca
      produz spec/checkpoint/manifest/snapshot cruzado (SC-005).

**Checkpoint**: SC-002, SC-003, SC-005 cobertos ponta a ponta.

**Adição além da lista original**:
`tests/integration/test_worker_pool_run_pool_orchestrator.py` (NOVO) —
T513–T515 provam `next_claimable_spec()`/`run_worker_loop()` isoladamente,
mas nenhuma task original exercitava `run_pool()` (o orquestrador real
chamado por `cli/main.py` para `--workers N > 1`) em si. Este teste (duplo
de processo via thread, `FakeBrowserTransport`) encontrou e permitiu
corrigir um bug real antes de qualquer execução real: `run_pool()` tentava
`snapshot.__dict__` sobre `MetricsSnapshot` (dataclass `slots=True` — sem
`__dict__`), o que teria derrubado o loop de métricas na primeira iteração
de qualquer run real com `--workers > 1`. Corrigido para
`dataclasses.asdict(snapshot)`.

---

## Fase 5: Métricas (US4)

- [x] T516 Criar `src/amayama_scraper/orchestration/metrics.py`:
      `MetricsSnapshot`, `query_metrics()` (leitura pura sobre `conn`,
      contracts/worker-pool-contract.md §4, FR-070/FR-071) — os 9 campos
      exigidos pelo item 8 do pedido do PO.
- [x] T517 `worker_pool.run_pool()`: loop de métricas do orquestrador emite
      `query_metrics()` a cada `--metrics-interval-seconds` (nunca por
      worker filho, FR-070).
- [x] T518 [P] `tests/unit/test_metrics_snapshot.py` (NOVO): estado de banco
      fabricado (contagens conhecidas de `checkpoint_entry`, `raw_capture`,
      `challenge_event`, `worker_heartbeat`, `rate_limiter_state`) produz os
      9 campos esperados; dois snapshots sucessivos produzem `groups/min`
      correto pela diferença.

**Checkpoint**: US4 coberto isoladamente.

---

## Fase 6: CLI (`--workers` e flags de configuração)

- [x] T519 `cli/options.py`: adicionar `--workers` (default `1`, validação
      `[1, 4]`, FR-001/FR-002), `--cdp-ports` (lista opcional, alternativa a
      derivar de `--cdp-port`), `--lease-seconds`, `--challenge-window-seconds`,
      `--challenge-threshold`, `--stability-seconds`,
      `--metrics-interval-seconds` (defaults documentados em plan.md
      "Decisões de design").
- [x] T520 `cli/main.py`: branch explícito — `--workers 1` chama
      `run_collection_driver()` exatamente como hoje (nenhuma linha nova no
      caminho de execução, FR-003); `--workers N > 1` chama
      `worker_pool.run_pool()`.
- [x] T521 [P] `tests/unit/test_cli_options_workers.py` (NOVO): `--workers 0`,
      `--workers 5`, `--workers -1` rejeitados antes de qualquer
      navegação/DB (FR-001).
- [x] T522 [P] `tests/integration/test_worker_pool_workers_one_parity.py`
      (NOVO): mesmo cenário fake rodado via `--workers 1` (novo branch) e
      via `run_collection_driver()` direto (caminho pré-005) produz
      exatamente os mesmos eventos/checkpoints (SC-001, US1).

**Checkpoint**: CLI completa; `--workers 1` comprovadamente idêntico ao
comportamento pré-005.

---

## Fase 7: Rate limiter fim-a-fim + resume (US3, US5)

- [x] T523 [P] `tests/integration/test_worker_pool_rate_limiter_reacts.py`
      (NOVO): `FakeBrowserTransport` servindo `CHALLENGE` para um subconjunto
      de specs — `effective_concurrency` cai conforme FR-063 e se recupera
      conforme FR-064 dentro do mesmo run, observável via
      `rate_limiter_repo.read_state()`.
- [x] T524 [P] `tests/integration/test_worker_pool_resume.py` (NOVO): banco
      pré-populado com specs `VALID`/`ACCEPTED` parciais (uma execução
      anterior, com ou sem pool) — `--resume <run_id> --workers 2` reivindica
      apenas specs pendentes, zero navegação para unidades já `ACCEPTED`
      (FR-090, FR-091, SC-005 via US5).

**Checkpoint**: US3 e US5 cobertos fim-a-fim.

---

## Fase 8: Validação final

- [x] T525 Rodar testes focados da feature 005 (`test_rate_limiter.py`,
      `test_lease_claim_semantics.py`, `test_metrics_snapshot.py`,
      `test_cli_options_workers.py`, `test_worker_pool_*.py`).
- [x] T526 Rodar suíte completa (`pytest -q`) — 001–004 permanecem 100%
      verdes (SC-001).
- [x] T527 `ruff check` nos arquivos alterados/criados.
- [x] T528 `mypy src`.
- [x] T529 Reportar ao PO: artefatos SDD, arquitetura final (processos vs.
      threads), estratégia de claim/lease, rate limiter, métricas
      adicionadas, testes, resultado completo da suíte, e o comando sugerido
      de benchmark 1×2 workers (quickstart.md) — **sem executá-lo** (exige
      coleta real, fora desta entrega).

**Nunca nesta fase ou em qualquer outra**: nenhuma task executa coleta real
nem `git commit`/`push` (instrução explícita do PO, Constitution/CLAUDE.md).

---

## Fase 9: Hardening pós-review (7 achados BLOCKER/HIGH)

**Contexto**: revisão técnica pós-entrega da feature 005 encontrou 2
BLOCKER e 5 HIGH. PO autorizou explicitamente a correção EXCLUSIVA desses 7
achados ("Corrija exclusivamente os 7 achados BLOCKER/HIGH... Não redesenhe
a feature além do necessário. Não procure melhorias fora destes achados.").
Nenhuma coleta real, nenhum commit.

- [x] T530 **BLOCKER — fencing de lease.** `spec_lease.lease_token`
      (INTEGER, migration `0009_worker_pool.sql` editada — feature ainda
      não fora enviada/mesclada, então a migration desta MESMA feature foi
      estendida em vez de criar uma nova) incrementa a cada
      claim/renovação/takeover (`lease_repo.try_claim()`/`renew_lease()`
      agora retornam `int | None`, o token, em vez de `bool`).
      `orchestration/worker_pool.py::_make_fenced_process_capture()`/
      `_make_fenced_finalize()` envolvem `process_capture()`/
      `try_finalize_spec_entry()` (injetados em `process_one_spec()`/
      `await_challenge_resolution()` via novos parâmetros
      `process_capture_fn`/`finalize_fn`, default = funções reais — zero
      mudança de comportamento para `--workers 1`) numa transação curta que
      primeiro confirma `(owner, lease_token)` contra o estado atual —
      `LeaseFencingError` antes de qualquer escrita se não confere.
      `_instrumented_on_event()`: renovação que retorna `None` (lease já
      tomado) levanta `LeaseFencingError` imediatamente. `run_worker_loop()`
      captura `LeaseFencingError`, emite `LEASE_LOST`, nunca
      libera/renova/persiste mais nada para aquela spec, segue para a
      próxima tentativa de claim (não derruba o worker).
      `try_finalize_spec_entry()` (pipeline.py) ganhou `run_in_transaction`
      opcional (default preserva comportamento exato) para permitir a
      composição do fencing com a transação de finalização, sem transação
      aninhada.
      **Testes**: `tests/unit/test_lease_fencing_token.py` (7 casos —
      token monotônico, takeover produz token maior, renovação por
      não-dono/depois de takeover falha) + cenário adversarial completo em
      `tests/integration/test_worker_pool_lease_fencing_adversarial.py`
      (worker A claim → lease expira → worker B recupera → grupo 2 de A é
      REJEITADO pelo fencing → B processa o grupo pendente e alcança
      VALID).
- [x] T531 **BLOCKER — reclaim infinito de specs sem progresso.**
      `process_one_spec()` retorna `SpecPassOutcome(should_backoff: bool)`
      (`True` quando nenhum `GROUP_ACCEPTED` ocorreu nesta passagem —
      challenge timeout, navegação rejeitada, ou só sobrou
      `REQUIRES_EXPLICIT_RETRY`). Novo `lease_repo.apply_backoff()`
      (estende `expires_at` sem trocar o dono) substitui `release_lease()`
      quando `should_backoff=True`. Novo `lease_repo.list_active_lease_spec_keys()`
      (independente do dono) usado por `next_claimable_spec()` para excluir
      QUALQUER spec com lease ativo da lista de candidatos — inclusive para
      o PRÓPRIO worker que aplicou o backoff (fecha a lacuna de "mesmo dono
      sempre pode renovar", que tornaria o backoff inútil contra
      auto-reclaim). `ClaimResult(claimed, throttled)` substitui o retorno
      `SpecIdentity | None` de `next_claimable_spec()` — `throttled=True`
      quando ainda há trabalho pendente em algum lugar (admissão sem slot,
      ou toda spec pendente já leased); `throttled=False` com
      `claimed=None` é o terminal genuíno (nada pendente, para ninguém).
      **Testes**: `tests/integration/test_worker_pool_no_infinite_reclaim.py`
      (3 casos — REQUIRES_EXPLICIT_RETRY nunca navega de novo e não é
      reclamado imediatamente mas volta a ser após o cooldown; challenge
      timeout idem; terminal genuíno quando tudo já é VALID).
- [x] T532 **BLOCKER — Ctrl+C/shutdown dos filhos.** `run_pool()` ganhou
      `stop_event: StopEventLike` (Protocol `is_set()`/`set()`, obrigatório
      — produção usa `multiprocessing.get_context("spawn").Event()`,
      construído em `cli/main.py::main()`) e `terminate_timeout`. Spawn +
      monitoramento de métricas agora rodam dentro de `try/finally`:
      `finally` sempre sinaliza `stop_event`, aguarda os filhos com
      timeout, `terminate()` os que sobrarem, e `join()` todos — antes de
      retornar OU de repropagar qualquer exceção (`KeyboardInterrupt`
      incluído, nunca capturada/engolida). `run_worker_loop()` checa
      `stop_event.is_set()` no topo do laço (entre specs) para
      encerramento cooperativo. Leases de workers interrompidos
      permanecem recuperáveis pelo mecanismo de expiração já existente
      (T514) — nenhuma mudança adicional necessária.
      **Teste**: `tests/integration/test_worker_pool_shutdown.py` —
      `sleep` do loop de métricas levanta `KeyboardInterrupt`
      propositalmente; um worker "ocupado" (thread que só sai ao ver
      `stop_event`) é observado saindo antes de `run_pool()` repropagar a
      exceção.
- [x] T533 **HIGH — exitcode de worker.** Após o `join()` final,
      `run_pool()` verifica `handle.exitcode` de cada worker; qualquer
      valor `!= 0`/`None` vira `WorkerProcessFailedError(failures)`
      (worker_index, cdp_port, exitcode). `cli/main.py`: `--workers N > 1`
      captura essa exceção → `stderr` + **exit code 7** (novo, documentado
      no docstring de `main()`) — nunca `return 0` quando um worker falhou.
      **Teste**: `tests/integration/test_worker_pool_worker_exitcode.py` —
      `worker_target` levanta `RuntimeError` propositalmente;
      `WorkerProcessFailedError.failures` confere worker/porta/exitcode=1.
- [x] T534 **HIGH — rate limiter matava workers permanentemente.**
      `next_claimable_spec()` (já reformulada em T531) devolve
      `throttled=True` quando o único motivo de não ter reivindicado nada é
      falta de slot — `run_worker_loop()` passa a tratar isso como
      "aguarda e tenta de novo" (`sleep(poll_interval); continue`) em vez
      de `return` — só encerra quando `throttled=False` (terminal
      genuíno), `stop_event` sinalizado, ou uma exceção fatal não-fencing
      propaga.
      **Teste**: `tests/integration/test_worker_pool_rate_limiter_pause_resume.py`
      — cenário exato pedido pela revisão (começa com 2, challenge reduz
      para 1, segundo worker permanece vivo tentando de novo — múltiplos
      eventos `WORKER_THROTTLED_WAITING_FOR_SLOT` observados —, estabilidade
      recupera para 2, segundo worker reivindica e completa a spec
      pendente).
- [x] T535 **HIGH — `FilesystemRawBlobStore` concorrente.**
      `persistence/blob_store.py::write_blob()`: arquivo temporário
      exclusivo por chamada (`{path.name}.{pid}.{uuid4}.tmp`, nunca um
      `.tmp` de nome fixo compartilhado); `Path.replace()` (atômico em
      todas as plataformas, inclusive Windows) publica o blob — se outro
      worker já publicou primeiro, sobrescreve atomicamente com o MESMO
      conteúdo (mesmo `content_hash`), nunca corrompe; `finally` limpa o
      tmp remanescente em caso de falha.
      `FilesystemRawBlobStore.get_or_create()`: `INSERT ... ON CONFLICT
      (content_hash) DO NOTHING` + releitura — nunca `IntegrityError` em
      colisão de PK, sempre retorna a linha vencedora (idempotência real).
      **Teste**: `tests/integration/test_filesystem_raw_blob_store_concurrent.py`
      — DOIS processos reais (`multiprocessing`, contexto `spawn`, não
      threads) publicando o MESMO `content_hash` concorrentemente; ambos
      saem com exitcode 0, exatamente 1 linha em `raw_blob`, conteúdo
      íntegro, zero `.tmp` remanescente.
- [x] T536 **HIGH — quickstart.md incorreto.** Benchmark 1×2 workers
      (`specs/005-performance-worker-pool/quickstart.md`, único lugar
      dentro de `specs/005-performance-worker-pool/` com o exemplo
      benchmark/CLI de GOL) corrigido de `--market AMA-BR` para
      `--market GL-BR`. Menções a `GOL_CONTEXT`/`AMA-BR` em spec.md/plan.md/
      tasks.md (fora do escopo deste achado) NÃO foram alteradas — são
      referências ao fixture de teste compartilhado `tests/support.py::
      GOL_CONTEXT` (herdado da feature 004, genuinamente `AMA-BR`), não
      exemplos de benchmark; alterá-las tornaria a documentação incorreta
      em relação ao código real.
- [x] T537 Rodar suíte completa (`pytest -q`) — 851 testes (001–005),
      feature 004 explicitamente re-executada (`-k "multi_model or
      collection_context or process_capture_context"`, 73 testes), suíte
      de hardening repetida 3x (`-k "worker_pool or lease_fencing or
      no_infinite_reclaim or filesystem_raw_blob_store_concurrent"`, 33
      testes cada vez) sem flakiness observada.
- [x] T538 `ruff check`/`ruff format --check` e `mypy src` — ambos limpos
      após o hardening.

**Checkpoint**: os 7 achados BLOCKER/HIGH corrigidos, com teste adversarial
dedicado para cada um; nenhuma regressão em 001–005; nenhum redesenho além
do necessário para os 7 pontos.

---

## Fase 10: Hardening pós-review — 2ª rodada (2 achados restantes)

**Contexto**: revisão focada sobre a Fase 9 encontrou 2 problemas
remanescentes: o backoff temporal (T531) não garantia terminalidade real
(uma spec sem progresso voltava a ser claimable assim que o cooldown
expirava, podendo repetir indefinidamente), e uma janela de race entre
`Process.start()` e o registro do handle no cleanup de `run_pool()`. PO
autorizou explicitamente a correção EXCLUSIVA desses 2 achados. Nenhuma
coleta real, nenhum commit, nenhum redesenho fora do necessário, nenhuma
busca por problemas novos.

- [x] T539 **BLOCKER — reclaim infinito depois do backoff (terminalidade
      real via disposição explícita, nunca backoff temporal).** Nova tabela
      `spec_pool_disposition` (`run_id + spec_key` → `state` +
      `pool_session_id`, migration `0009_worker_pool.sql` estendida — ainda
      não enviada/mesclada) e novo repositório
      `persistence/repositories/spec_pool_disposition_repo.py`
      (`get`/`set_manual_retry_required`/`set_deferred_this_session`/
      `clear`). `lease_repo.apply_backoff()` **removido** (nenhum outro
      chamador; o mecanismo de cooldown temporal deixou de existir —
      `lease_repo.list_active_lease_spec_keys()` continua servindo apenas
      admissão + exclusão de leases ativos em tempo real, nunca
      terminalidade).
      `collection_driver.py`: `SpecPassOutcome.should_backoff` (bool)
      virou `SpecPassOutcome.disposition: SpecPassDisposition`
      (`PROGRESSED`/`MANUAL_RETRY_REQUIRED`/`DEFERRED_THIS_SESSION`) —
      `MANUAL_RETRY_REQUIRED` quando pelo menos um grupo foi classificado
      `GROUP_REJECTED_AWAITING_MANUAL_RETRY` nesta passagem;
      `DEFERRED_THIS_SESSION` para challenge timeout/navegação rejeitada
      sem nenhuma unidade exigindo retry manual; `PROGRESSED` quando houve
      ao menos um `GROUP_ACCEPTED`.
      `worker_pool.py`: `next_claimable_spec()` ganhou `pool_session_id`
      (obrigatório) e um novo `_is_eligible()` que exclui
      `MANUAL_RETRY_REQUIRED` (a menos que `--retry-rejected`) e
      `DEFERRED_THIS_SESSION` só quando `pool_session_id` bate com o
      registrado — independente de tempo. `run_worker_loop()` ganhou
      `pool_session_id` (obrigatório, repassado a `next_claimable_spec()`);
      ao final de cada passagem, grava a disposição correspondente
      (`PROGRESSED` → `clear()`) e **sempre** libera o lease normalmente
      (nunca mais estende `expires_at` como cooldown). `run_pool()` gera
      `pool_session_id = str(uuid.uuid4())` UMA vez por invocação e
      repassa a todos os workers via `WorkerProcessArgs` (novo campo
      `pool_session_id`) — uma nova invocação (`--resume`) gera outro
      valor, reabrindo `DEFERRED_THIS_SESSION` automaticamente.
      **Testes**: `tests/unit/test_spec_pool_disposition.py` (7 casos, nível
      de repositório) + `tests/integration/test_worker_pool_no_infinite_reclaim.py`
      reescrito com os 3 cenários exigidos pela revisão: (1) challenge
      timeout → deferred, nunca reclamada na mesma `run_pool()`, pool
      atinge terminal sozinho, `--resume` (nova sessão) tenta de novo com
      sucesso; (2) retry manual → não reclamada no mesmo pool nem numa nova
      execução normal, só `--retry-rejected` permite nova tentativa (e
      limpa a disposição ao progredir); (3) dois workers com apenas specs
      deferred/manual restantes — ambos retornam (`run_worker_loop()`)
      sem jamais navegar, provando ausência de loop de polling/reclaim
      infinito. Nenhum sleep longo — clocks avançados manualmente via
      `sleep=` injetado.
- [x] T540 **HIGH — race entre `Process.start()` e registro do filho.**
      `run_pool()`: `workers.append((index, cdp_port, handle))` agora
      acontece ANTES de `handle.start()` (nunca depois). `_ProcessHandle`
      (Protocol) ganhou `pid: int | None` — `None` até `start()`
      efetivamente criar o processo/thread real, nunca `None` depois
      (mesma semântica pública de `multiprocessing.Process.pid`). O
      cleanup em `finally` checa `handle.pid is not None` antes de cada
      `join()`/`terminate()`/`is_alive()` — nunca invoca essas operações
      num handle registrado cujo `start()` não chegou a criar o filho real
      (ambos `multiprocessing.Process` e o double de teste levantam erro
      nessas chamadas antes de iniciar); todo processo que chegou a
      iniciar passa por `join()` obrigatoriamente. `tests/support.py::ThreadProcessHandle`
      ganhou `pid` (espelha `threading.Thread.ident`).
      **Teste adversarial**: `tests/integration/test_worker_pool_start_race.py`
      — `_InterruptingStartHandle` inicia o filho real (thread viva)
      DENTRO de `start()` e só então levanta `KeyboardInterrupt` (o
      cenário exato do achado); prova que o handle já registrado é
      join()ado corretamente (worker cooperativo observa `stop_event` e
      retorna) e que `KeyboardInterrupt` continua propagando depois do
      cleanup. `_FailingStartHandle` — `start()` falha ANTES de qualquer
      criação real (`pid` sempre `None`); `join()`/`is_alive()`/`terminate()`
      levantam `AssertionError` se chamados, provando que `run_pool()`
      nunca os invoca nesse caso (o `OSError` original continua
      propagando, sem ser mascarado por uma exceção levantada dentro do
      `finally`).
- [x] T541 Rodar suíte completa (`pytest -q`) — 859 testes (001–005),
      feature 004 explicitamente re-executada (73 testes), suíte de
      concorrência/hardening (`worker_pool`, `lease_fencing`,
      `no_infinite_reclaim`, `filesystem_raw_blob_store_concurrent`,
      `spec_pool_disposition`, `start_race`) repetida 3x (41 testes cada
      vez) sem flakiness.
- [x] T542 `ruff check`/`ruff format --check` e `mypy src` — ambos limpos.

**Checkpoint**: terminalidade do worker pool garantida por disposição
explícita (nunca tempo); nenhuma janela entre `Process.start()` e o
registro do handle monitorado; nenhuma regressão em 001–005; nenhum
redesenho fora dos 2 achados.

---

## Dependencies & Execution Order

Fase 1 bloqueia todas as demais (migration + rate limiter puro). Fase 2
depende da Fase 1 (schema). Fase 3 é independente das Fases 1–2 (extração
mecânica) mas deve completar antes da Fase 4 (worker_pool reusa
`process_one_spec()`). Fase 4 depende de Fases 1–3. Fase 5 depende de Fases
1–2 (lê as mesmas tabelas) e pode rodar em paralelo com a Fase 4. Fase 6
depende de Fases 4–5 (CLI compõe orquestrador + métricas). Fase 7 depende da
Fase 6 (fim-a-fim via CLI/fakes). Fase 8 valida o estado pré-hardening. Fase
9 (hardening pós-review) depende de Fases 1–8 completas e altera
`lease_repo.py`/`worker_pool.py`/`collection_driver.py`/`pipeline.py`/
`cli/main.py`/`blob_store.py`/`filesystem_raw_blob_store.py`. Fase 10
(hardening pós-review, 2ª rodada) depende da Fase 9 completa e altera os
mesmos módulos de `worker_pool.py`/`collection_driver.py`/`cli/main.py` +
o novo `spec_pool_disposition_repo.py` — é sempre a última.

## Notes

- Todas as tasks foram executadas nesta conversa, sob autorização explícita
  do PO ("PO APPROVAL — Feature 005"; hardening pós-review autorizado em
  mensagem subsequente, escopo restrito aos 7 achados BLOCKER/HIGH; 2ª
  rodada de hardening autorizada em mensagem subsequente, escopo restrito
  aos 2 achados remanescentes). Resultado final (pós-hardening, 2ª rodada):
  859 testes (001–005) passando, `ruff check`/`ruff format --check`/
  `mypy src` limpos.
- `parsing/*`, `equivalence/*`, `fingerprints/*`, `snapshots/*`,
  `normalization/*`, `assets/*`, `validation/detectors/*` (challenge
  incluído) e `analysis/*` (003) não têm nenhuma task nesta lista —
  permanecem intocados por design (spec.md "Assumptions").
- O benchmark real 1×2 workers (item 14 do pedido do PO) não é uma task
  desta lista — depende de implementação aprovada e executada, e de coleta
  real, ambos fora do escopo desta entrega.
