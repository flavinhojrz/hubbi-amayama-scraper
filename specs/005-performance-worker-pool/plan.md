# Implementation Plan: Performance Worker Pool — Paralelismo Controlado por Spec

**Branch**: `005-performance-worker-pool` | **Date**: 2026-09-03 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/005-performance-worker-pool/spec.md`

## Summary

Introduzir paralelismo **entre specs** (nunca dentro de uma spec) via um pool
de processos de SO independentes, coordenados por claim/lease atômico sobre
SQLite (`BEGIN IMMEDIATE` + upsert condicional) e por um rate limiter
adaptativo determinístico que reage a challenges observados. `--workers 1`
(default) permanece exatamente o código/comportamento de hoje —
`run_collection_driver()` não é alterado no seu caminho de execução; a
lógica por-spec é extraída para uma função compartilhada
(`process_one_spec()`) reutilizada tanto pelo laço legado quanto pelo laço
de worker com lease, garantindo paridade estrita de comportamento. Nenhuma
mudança em parsing, fingerprints, normalização, equivalência, snapshots,
detecção de challenge, ou nas validações de contexto da feature 004 — todas
reutilizadas sem alteração. Nenhuma coleta real, nenhum commit (instrução
explícita do PO).

## Technical Context

**Language/Version**: Python 3.11 (mypy strict)

**Primary Dependencies**: stdlib `multiprocessing` (contexto `spawn` —
único suportado no Windows, ambiente do PO), `sqlite3`, `selenium` (já
existente, isolado em `transport/chrome_cdp_adapter.py`) — nenhuma
dependência nova em `pyproject.toml`.

**Storage**: SQLite (`amayama.db`), WAL — schema estendido por uma migration
puramente aditiva (`0009_worker_pool.sql`, 4 tabelas novas, zero `ALTER
TABLE`). Ver [data-model.md](./data-model.md).

**Testing**: pytest (`tests/unit` para lease/rate-limiter/métricas como
funções puras; `tests/integration` para concorrência real com
`multiprocessing`/SQLite em arquivo temporário e para paridade `--workers 1`).

**Target Platform**: Windows/PowerShell (ambiente do PO) — `multiprocessing`
usa `spawn` nativamente no Windows, então nenhuma configuração adicional é
necessária; Linux (CI) também suportado via `spawn` explícito.

**Project Type**: single project (CLI + biblioteca de domínio) — inalterado.

**Performance Goals**: throughput real (grupos/min) maior com `--workers 2`
do que com `--workers 1` **sob taxa de challenge estável** — não garantido
por construção (o próprio pedido do PO alerta: "não suponha que mais
workers = mais rápido"); esta entrega não mede isso (nenhuma coleta real),
apenas prepara o comando de benchmark (Quickstart, Fase de validação real).

**Constraints**: nenhuma coleta real; nenhum commit; nenhuma migração
destrutiva; `--workers 1` bit-a-bit idêntico ao pipeline pré-005; nenhum
bypass de CAPTCHA/challenge; nenhuma alteração ao isolamento de contexto da
feature 004; nenhum novo import de `selenium` fora de
`transport/chrome_cdp_adapter.py`.

**Scale/Scope**: até 4 workers (`--workers` em `[1, 4]`, FR-001); mesmo
escopo de dados de 002/004 (Volkswagen/Amayama, multi-modelo).

## Constitution Check

*GATE: relido antes desta fase (Constitution §5, §6, §11, §12, §14; ver
CLAUDE.md/EXECUTION_POLICY.md).*

- **§5 (Coleta e segurança)**: nenhum bypass de CAPTCHA/challenge —
  `await_challenge_resolution()` inalterado; cada worker pausa
  human-in-the-loop na sua própria janela (FR-050). **Passa.**
- **§6 (Separação de responsabilidades)**: claim/lease e rate limiter vivem
  em `persistence/repositories/` (I/O) + `orchestration/rate_limiter.py`
  (função pura, sem I/O) — mesmo padrão já usado por
  `checkpoint_entry.transition()` (pura) + `checkpoint_repo.upsert_checkpoint_entry()`
  (I/O). `worker_pool.py` é composição raiz (como `collection_driver.py` já
  é), nunca reimplementa parsing/validação/domínio. **Passa.**
- **§11 (Snapshots e revalidação)**: nenhuma mudança em `SpecSnapshot`,
  estados (VALID/INCOMPLETE/STALE/SUPERSEDED/INVALID), ou critério de
  representante — o worker pool não decide equivalência, apenas ordena
  *quando* cada spec é processada. **Passa.**
- **§12 (Qualidade e testes)**: toda regra estrutural nova (FR-001 a
  FR-101) tem teste correspondente na Fase de tasks abaixo, incluindo os 9
  cenários exigidos pelo item 12 do pedido do PO. **Passa.**
- **§14 (Gates)**: esta entrega para no gate `TASKS → PO APPROVAL` — nenhum
  `CLAUDE IMPLEMENTA` é iniciado sem autorização explícita subsequente do PO
  (ver "Gate desta entrega" abaixo). **Passa.**
- **Gate PASSA.** Nenhuma violação a justificar em Complexity Tracking.

## Gate desta entrega (Execution Policy)

O pedido inicial do PO nesta conversa foi explicitamente **"criar a feature
`005-performance-worker-pool`"** com os três artefatos SDD — sem a
autorização direta de `CLAUDE IMPLEMENTA` que a feature 004 registrou na
mesma conversa em que foi pedida. `tasks.md` foi entregue como lista
aprovável, sem nenhuma task marcada como executada.

Em mensagem subsequente ("PO APPROVAL — Feature 005"), o PO aprovou
explicitamente `spec.md`/`plan.md`/`data-model.md`/
`contracts/worker-pool-contract.md`/`quickstart.md`/`tasks.md` e autorizou
`CLAUDE IMPLEMENTA` — todas as tasks de `tasks.md` foram então executadas
nesta mesma conversa (código, migration, testes reais, `ruff`/`mypy`).
Nenhuma coleta real e nenhum commit foram executados (restrições explícitas
do PO na própria autorização) — o benchmark do item 14 continua fora do
escopo desta entrega.

## Project Structure

### Documentation (this feature)

```text
specs/005-performance-worker-pool/
├── spec.md                              # especificação (User Stories, FRs, SC)
├── plan.md                              # este arquivo
├── data-model.md                        # spec_lease, rate_limiter_state, challenge_event, worker_heartbeat
├── contracts/
│   └── worker-pool-contract.md          # topologia processos/lease/rate-limiter/métricas
├── quickstart.md                        # como abrir N Chromes, comando --workers, benchmark
└── tasks.md                             # lista de tasks executável (aguardando aprovação do PO)
```

### Source Code (repository root)

```text
src/amayama_scraper/
├── persistence/
│   ├── migrations/
│   │   └── 0009_worker_pool.sql          # NOVO — spec_lease, rate_limiter_state,
│   │                                       #        challenge_event, worker_heartbeat
│   └── repositories/
│       ├── lease_repo.py                 # NOVO — try_claim/renew_lease/release_lease/
│       │                                   #        count_active_leases (I/O puro, transacional)
│       ├── rate_limiter_repo.py          # NOVO — read/write rate_limiter_state (I/O),
│       │                                   #        delega a decisão a orchestration/rate_limiter.py
│       ├── challenge_event_repo.py       # NOVO — record_challenge_event/count_in_window
│       └── worker_heartbeat_repo.py      # NOVO — upsert_heartbeat/count_active
├── orchestration/
│   ├── rate_limiter.py                   # NOVO — RateLimiterState/Config,
│   │                                       #        on_challenge_observed()/on_stability_tick()
│   │                                       #        (funções puras, sem I/O — contracts/worker-pool-contract.md §4)
│   ├── metrics.py                        # NOVO — MetricsSnapshot, query_metrics() (leitura pura)
│   ├── worker_pool.py                    # NOVO — worker_main(), next_claimable_spec(),
│   │                                       #        orquestrador (spawn, join, loop de métricas)
│   └── collection_driver.py              # process_one_spec() extraído do laço
│                                           # `for spec in specs_to_process` de
│                                           # run_collection_driver() — reusado por AMBOS os
│                                           # caminhos (--workers 1 legado E worker_pool.py);
│                                           # run_collection_driver() em si NÃO muda de
│                                           # comportamento, apenas passa a chamar a função
│                                           # extraída em vez de código inline
└── cli/
    ├── options.py                        # + --workers, --lease-seconds,
    │                                       #   --challenge-window-seconds, --challenge-threshold,
    │                                       #   --stability-seconds, --metrics-interval-seconds,
    │                                       #   --cdp-ports (lista explícita, alternativa a
    │                                       #   derivar de --cdp-port/--cdp-port-base)
    └── main.py                           # branch: --workers 1 → run_collection_driver()
                                            # inalterado; --workers N>1 → worker_pool.run_pool()

tests/
├── unit/
│   ├── test_rate_limiter.py              # NOVO — FR-060 a FR-065, função pura (SC-004)
│   ├── test_lease_claim_semantics.py     # NOVO — FR-020 a FR-025, transação simulada
│   ├── test_metrics_snapshot.py          # NOVO — FR-070/FR-071, leitura pura sobre estado fabricado
│   └── test_cli_options_workers.py       # NOVO — --workers fora de [1,4] rejeitado (FR-001)
├── integration/
│   ├── test_worker_pool_no_double_claim.py     # NOVO — SC-002, dois workers reais (multiprocessing
│   │                                             # ou threads simulando processos via DB real)
│   ├── test_worker_pool_lease_recovery.py      # NOVO — SC-003
│   ├── test_worker_pool_workers_one_parity.py  # NOVO — SC-001 (US1): --workers 1 produz
│   │                                             #        exatamente os mesmos eventos/checkpoints
│   │                                             #        que o pipeline pré-005
│   ├── test_worker_pool_rate_limiter_reacts.py # NOVO — US3 fim-a-fim (FakeBrowserTransport
│   │                                             #        servindo CHALLENGE)
│   ├── test_worker_pool_resume.py              # NOVO — SC-005/US5 (resume + --workers)
│   └── test_worker_pool_context_isolation.py   # NOVO — US6, reusa AMAROK_CONTEXT/GOL_CONTEXT
│                                                 #        de tests/support.py (004)
└── support.py                                   # + fábricas de SpecLease/RateLimiterState
                                                    #   para os testes acima, se necessário
```

**Structure Decision**: projeto single (já estabelecido por 001–004). O
padrão "regra pura em `orchestration/` (ou `domain/`) + persistência fina em
`persistence/repositories/`" já usado por `checkpoint_entry.transition()` +
`checkpoint_repo.py` é replicado para `rate_limiter.py` +
`rate_limiter_repo.py` — nenhuma abstração nova é inventada, apenas o mesmo
padrão já validado no projeto. `worker_pool.py` entra em `orchestration/`
pelo mesmo motivo que `collection_driver.py` já está lá: é composição raiz
(conhece domínio + adapters concretos), nunca reimplementa regra de negócio.

## Decisões de design (revisão do PO no gate de PLAN)

Diferente de "Assumptions" de requisito (spec.md), estas são escolhas de
arquitetura dentro do espaço já delimitado pelo pedido do PO — registradas
aqui explicitamente para que o PO possa corrigi-las antes do gate de TASKS,
sem que isso signifique que foram tratadas como ambiguidade de requisito não
resolvida:

1. **Processos via `multiprocessing` (spawn), não `subprocess` reinvocando a
   CLI** — evita reserializar `CollectionContext`/filtros via argv; usa o
   mesmo interpretador/venv do processo pai.
2. **Porta CDP por worker**: `--cdp-ports 9222,9223,9224,9225` (lista
   explícita, tamanho == `--workers`) como via primária; se omitida,
   deriva de `--cdp-port` (ou default 9222) como base + índice do worker.
   Documentado em `quickstart.md`.
3. **MARKET_INDEX (Nível A) sempre sequencial**, executado pelo processo
   orquestrador antes de qualquer spawn — nunca paralelizado (não há mais
   de uma página de índice por run; paralelizar não traria ganho e
   complicaria o tratamento do challenge inicial).
4. **`_maybe_mark_run_completed()` só roda no orquestrador, após `join()`
   de todos os workers** (nunca em worker filho) — elimina qualquer
   corrida sobre esse cálculo sem precisar de lock adicional.
5. **Defaults sugeridos** (todos configuráveis via CLI, nenhum
   hardcoded fora de `cli/options.py`):
   - `--lease-seconds 120` (deve exceder confortavelmente o tempo típico de
     um `GROUP_DETAIL` + margem de rede).
   - `--challenge-window-seconds 300`, `--challenge-threshold 1` (primeiro
     challenge dentro de 5 minutos já degrada a concorrência em 1 — postura
     conservadora, alinhada a "priorizando... integridade").
   - `--stability-seconds 600` (10 minutos limpos para recuperar 1 nível de
     concorrência).
   - `--metrics-interval-seconds 30`.
6. **Falha de um worker ao iniciar não derruba o pool** (Chrome daquela
   porta não aberto) — reportada, os demais continuam; run falha apenas se
   nenhum worker consegue iniciar.

## Complexity Tracking

Nenhuma violação de Constitution Check — tabela não aplicável.
