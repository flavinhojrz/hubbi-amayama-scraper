# Contrato: Worker Pool (claim/lease, processos, rate limiter)

**Feature**: `005-performance-worker-pool` — ver [../spec.md](../spec.md),
[../data-model.md](../data-model.md).

## 0. Por que processos, nunca threads (FR-040, FR-041)

`ChromeCdpTransport` (`transport/chrome_cdp_adapter.py`) encapsula um único
`webdriver.Chrome` anexado via `debuggerAddress` a **um** Chrome real. O
estado exposto (`driver.page_source`, `driver.current_url`) é global à
sessão anexada — não há isolamento por chamada. Duas threads chamando
`navigate()`/`current_capture()` no mesmo `ChromeCdpTransport` poderiam:

- Ler `page_source` de uma navegação que não foi a que a própria thread
  disparou (a segunda `driver.get()` sobrescreve o estado antes da primeira
  thread ler o resultado).
- Persistir uma `RawCaptureInput` como se fosse de uma spec, contendo na
  verdade o HTML de outra — corrupção silenciosa, sem qualquer exceção,
  inaceitável pela Constitution §4 (raw imutável e auditável) e §6
  (separação de responsabilidades — o transporte nunca decide o que
  representa, mas também nunca pode *misturar* o que representa).

Solução: **um processo de SO por worker**, cada um com seu próprio
`ChromeCdpTransport` anexado a um Chrome real distinto (host/porta próprios).
Processos não compartilham memória — impossível haver a corrida acima por
construção, não por disciplina de lock.

`multiprocessing` (contexto `spawn`, único suportado no Windows — ambiente
do PO) é o mecanismo escolhido, em vez de `subprocess` reinvocando a CLI:
permite passar `CollectionContext`/`OperationalFilters`/config já validados
como objetos Python picklable diretamente para `worker_main()`, sem
serializar/reparsear argv por processo filho.

## 1. Topologia: orquestrador + N workers

```
cli/main.py (--workers N > 1)
  │
  ├─ 1. Nível A (MARKET_INDEX) — executado pelo PRÓPRIO processo
  │     orquestrador, usando o ChromeCdpTransport da porta[0]. Mesmo
  │     código/comportamento de hoje (run_collection_driver, Nível A),
  │     extraído para uma função reutilizável — inclui o challenge
  │     human-in-the-loop se ocorrer aqui.
  │
  ├─ 2. Após MARKET_INDEX aceito (ou critical_error → RUN_ABORTED, igual
  │     hoje): spawn de N processos worker (multiprocessing, contexto
  │     spawn), cada um com:
  │       - run_id, CollectionContext (picklable, imutável)
  │       - host/porta CDP própria (porta[i], i=0..N-1 — worker 0 reusa a
  │         MESMA porta do orquestrador, mas SEQUENCIALMENTE: o
  │         orquestrador encerra seu ChromeCdpTransport antes do worker 0
  │         anexar — nunca dois drivers vivos simultâneos na mesma janela
  │         de Chrome, ver §5 "Riscos")
  │       - OperationalFilters, poll_interval, challenge_timeout,
  │         min_interval (idênticos aos de hoje)
  │       - worker_id (ex. f"{run_id}:{i}:{pid}")
  │       - config do rate limiter/lease (lease_seconds,
  │         challenge_window_seconds, challenge_threshold,
  │         stability_seconds)
  │
  ├─ 3. Loop do orquestrador enquanto workers vivos:
  │       sleep(metrics_interval_seconds)
  │       snapshot = query_metrics(conn_readonly, run_id, context)  # FR-070
  │       print(snapshot)
  │
  └─ 4. join() em todos os workers → _maybe_mark_run_completed() UMA VEZ
        (FR-033) → RUN_SUMMARY final (reuso do formato já existente).
```

## 2. Corpo de um worker (`orchestration/worker_pool.py::worker_main`)

```
worker_main(run_id, context, cdp_host, cdp_port, filters, poll_interval,
            challenge_timeout, min_interval, worker_id, lease_config,
            db_path, raw_root):

  conn = connect(db_path)                       # própria conexão (FR-030)
  transport = ChromeCdpTransport(cdp_host, cdp_port)   # própria sessão (FR-040)
  blob_store, capture_repo = ...                 # mesmos adapters de hoje

  while True:
      candidate = next_claimable_spec(conn, run_id, context, worker_id,
                                       lease_config)     # FR-020, FR-062
      if candidate is None:
          break                                  # nada mais a reivindicar — encerra

      process_one_spec(transport, conn, blob_store, capture_repo,
                        run_id=run_id, context=context, spec=candidate,
                        filters=filters, poll_interval=poll_interval,
                        challenge_timeout=challenge_timeout,
                        min_interval=min_interval,
                        renew_lease=lambda: renew_lease(conn, run_id,
                                                         candidate.stable_key(),
                                                         worker_id, lease_config),
                        record_challenge=lambda **kw: record_challenge_event(
                            conn, run_id, worker_id, **kw),   # FR-051
                        on_event=on_event)

      release_lease(conn, run_id, candidate.stable_key(), worker_id)  # FR-025
```

`process_one_spec()` é a mesma lógica que hoje vive inline no laço
`for spec in specs_to_process` de `run_collection_driver()` (SPEC_NAVIGATION
→ grupos pendentes → GROUP_DETAIL → `try_finalize_spec_entry`) — extraída
para uma função compartilhada, chamada tanto pelo caminho legado
(`--workers 1`, iterando specs sequencialmente, SEM lease) quanto pelo laço
acima (com lease). **Nenhuma regra de domínio/validação é reimplementada**
— reuso estrito de `process_capture`/`await_challenge_resolution`/
`try_finalize_spec_entry`, exatamente como hoje.

## 3. `next_claimable_spec()` — seleção + claim em um único passo (FR-020, FR-062)

```
next_claimable_spec(conn, run_id, context, worker_id, lease_config):
  with transaction(conn):                        # BEGIN IMMEDIATE (FR-031: curta)
      effective_concurrency = read_rate_limiter_state(conn, run_id).effective_concurrency
      active_leases = count_active_leases(conn, run_id, now())     # expires_at > now
      if active_leases >= effective_concurrency:
          return None                              # US3 Cenário 3 — recua, não reivindica

      all_specs = list_by_scope(conn, ...)          # mesma leitura de hoje
      for spec in apply_operational_filters(all_specs, filters):
          if get_current_state(conn, spec.stable_key()) is not None:
              continue                              # já VALID/STALE — nunca reivindicada (FR-024)
          if try_claim(conn, run_id, spec.stable_key(), worker_id, lease_config):
              return spec
      return None                                   # nada pendente — worker encerra
```

`try_claim()` é exatamente a operação SQL de `data-model.md` §1 — dentro da
MESMA transação da leitura acima, garantindo que a checagem de
`effective_concurrency` e a reivindicação sejam atômicas entre si (nunca dois
workers leem "ainda há slot" e ambos reivindicam além do limite).

## 4. Métricas (`orchestration/metrics.py::query_metrics`, FR-070/FR-071)

Função pura de leitura (sem mutação), parametrizada por dois snapshots
consecutivos para `grupos/min`:

```python
@dataclass(frozen=True, slots=True)
class MetricsSnapshot:
    specs_completed: int
    groups_accepted: int
    groups_per_minute: float
    requests_total: int
    challenges_total: int
    challenges_per_hour: float
    challenge_wait_seconds_total: float
    active_workers: int
    effective_concurrency: int

def query_metrics(conn, run_id, context, previous, now) -> MetricsSnapshot: ...
```

Todas as fontes já existem ou são as tabelas de `data-model.md`:
`current_spec_state` (via `list_by_scope`/`get_current_state`),
`checkpoint_entry` (`COUNT(*) WHERE status='ACCEPTED'`), `raw_capture`
(`COUNT(*) WHERE run_id=?`), `challenge_event`, `worker_heartbeat`,
`rate_limiter_state`. Emitida exclusivamente pelo orquestrador (nunca por
worker filho — FR-070), evitando linhas de métrica duplicadas/intercaladas
de processos concorrentes no stdout.

## 5. Riscos e mitigação

- **Worker 0 reanexando à porta do orquestrador**: o orquestrador cria seu
  próprio `ChromeCdpTransport(porta[0])` só para o Nível A (MARKET_INDEX) e
  o descarta (nenhuma referência retida) antes de dar spawn no worker 0, que
  cria um `ChromeCdpTransport` novo na mesma porta — sequenciado, nunca
  concorrente. Validado empiricamente no benchmark real (item 14 do pedido
  do PO, fora desta entrega) antes de qualquer recomendação de uso em
  produção com N > 1.
- **Falha de um worker ao iniciar** (`ChromeNotReachableError` numa porta
  sem Chrome aberto): reportada por worker, não derruba os demais (Edge
  Cases de spec.md) — decisão de design registrada para revisão do PO no
  gate de PLAN, não uma suposição sobre requisito de produto.
- **`effective_concurrency` e leases lidos em transações separadas por
  workers diferentes**: cada leitura+claim é uma única transação
  `BEGIN IMMEDIATE` (§3) — o SQLite serializa escritores reais entre
  processos (já configurado, `busy_timeout=5000`), então não há dupla
  contagem de slot mesmo com N processos competindo.
