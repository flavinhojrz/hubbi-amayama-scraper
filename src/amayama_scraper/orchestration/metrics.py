"""metrics.py — snapshot periódico de métricas do worker pool (005, US4;
contracts/worker-pool-contract.md §4, FR-070/FR-071).

Leitura pura sobre `conn` (nenhuma mutação) — os 9 campos exigidos pelo
pedido do PO, todos derivados de estado já persistido (checkpoint_entry,
current_spec_state via list_by_scope/get_current_state, raw_capture,
challenge_event, worker_heartbeat, rate_limiter_state). Emitido
exclusivamente pelo processo orquestrador (`orchestration/worker_pool.py::
run_pool()`), nunca por worker filho — evita linhas de métrica
duplicadas/intercaladas de processos concorrentes.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from amayama_scraper.domain.collection_context import CollectionContext
from amayama_scraper.orchestration.rate_limiter import RateLimiterConfig
from amayama_scraper.persistence.repositories import challenge_event_repo, rate_limiter_repo
from amayama_scraper.persistence.repositories import worker_heartbeat_repo as heartbeat_repo
from amayama_scraper.persistence.repositories.current_state_repo import get_current_state
from amayama_scraper.persistence.repositories.spec_registry_repo import list_by_scope


class _PoolConfigLike(Protocol):
    """Duck-typing de `orchestration.worker_pool.WorkerPoolConfig` — evita
    import circular (`worker_pool.py` já importa este módulo). Declarado via
    `@property` (não um atributo simples) para casar estruturalmente com um
    dataclass congelado (`frozen=True` — atributo somente-leitura)."""

    @property
    def heartbeat_staleness_seconds(self) -> float: ...

    def rate_limiter_config(self) -> RateLimiterConfig: ...


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


def _count_specs_completed(conn: sqlite3.Connection, context: CollectionContext) -> int:
    specs = list_by_scope(
        conn,
        manufacturer=context.manufacturer,
        vehicle_model=context.vehicle_model,
        market=context.market,
    )
    return sum(1 for spec in specs if get_current_state(conn, spec.stable_key()) is not None)


def _count_groups_accepted(conn: sqlite3.Connection, run_id: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM checkpoint_entry WHERE run_id = ? AND status = 'ACCEPTED'",
        (run_id,),
    ).fetchone()
    return int(row["n"])


def _count_requests_total(conn: sqlite3.Connection, run_id: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM raw_capture WHERE run_id = ?", (run_id,)
    ).fetchone()
    return int(row["n"])


def query_metrics(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    context: CollectionContext,
    previous: MetricsSnapshot | None,
    previous_at: datetime,
    now: datetime,
    pool_config: _PoolConfigLike,
) -> MetricsSnapshot:
    """`groups_per_minute` é derivado da diferença entre `previous` (snapshot
    anterior, `None` na primeira chamada) e o valor atual, dividida pelo
    tempo decorrido em minutos (`now - previous_at`) — nunca do total desde
    o início do run (US4, "Acceptance Scenarios" — dois snapshots sucessivos
    produzem o valor correto pela diferença)."""
    rate_config = pool_config.rate_limiter_config()
    staleness = pool_config.heartbeat_staleness_seconds

    groups_accepted = _count_groups_accepted(conn, run_id)
    elapsed_minutes = max((now - previous_at).total_seconds() / 60.0, 1e-9)
    groups_per_minute = (
        0.0
        if previous is None
        else max(0.0, (groups_accepted - previous.groups_accepted) / elapsed_minutes)
    )

    state = rate_limiter_repo.read_state(conn, run_id=run_id, config=rate_config, now=now)

    return MetricsSnapshot(
        specs_completed=_count_specs_completed(conn, context),
        groups_accepted=groups_accepted,
        groups_per_minute=groups_per_minute,
        requests_total=_count_requests_total(conn, run_id),
        challenges_total=challenge_event_repo.count_total(conn, run_id=run_id),
        challenges_per_hour=float(
            challenge_event_repo.count_in_trailing_hour(conn, run_id=run_id, now=now)
        ),
        challenge_wait_seconds_total=challenge_event_repo.total_wait_seconds(conn, run_id=run_id),
        active_workers=heartbeat_repo.count_active(
            conn, run_id=run_id, now=now, staleness_seconds=staleness
        ),
        effective_concurrency=state.effective_concurrency,
    )


__all__ = ["MetricsSnapshot", "query_metrics"]
