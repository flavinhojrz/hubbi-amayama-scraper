"""rate_limiter_repo.py — persistência fina de `rate_limiter_state` (005, US3;
data-model.md §2).

Lê/grava o estado; nunca decide a política — a decisão pura vive em
`orchestration/rate_limiter.py` (Constitution §6). Declarações simples
(autocommit), compõem sem aninhar `BEGIN` dentro da transação maior de
`worker_pool.next_claimable_spec()`, mesmo padrão de `lease_repo.py`.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from amayama_scraper.orchestration.rate_limiter import (
    RateLimiterConfig,
    RateLimiterState,
    initial_state,
)


def read_state(
    conn: sqlite3.Connection, *, run_id: str, config: RateLimiterConfig, now: datetime
) -> RateLimiterState:
    """Lazy-init (plan.md "Decisões de design"): a primeira leitura de um
    `run_id` sem linha ainda grava e retorna `initial_state()` (concorrência
    efetiva no teto `config.max_concurrency`, FR-060)."""
    row = conn.execute(
        "SELECT effective_concurrency, stable_since FROM rate_limiter_state WHERE run_id = ?",
        (run_id,),
    ).fetchone()
    if row is None:
        state = initial_state(config, started_at=now)
        write_state(conn, run_id=run_id, state=state, now=now)
        return state
    return RateLimiterState(
        effective_concurrency=row["effective_concurrency"],
        stable_since=datetime.fromisoformat(row["stable_since"]),
    )


def write_state(
    conn: sqlite3.Connection, *, run_id: str, state: RateLimiterState, now: datetime
) -> None:
    conn.execute(
        """
        INSERT INTO rate_limiter_state (run_id, effective_concurrency, stable_since, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT (run_id) DO UPDATE SET
            effective_concurrency = excluded.effective_concurrency,
            stable_since = excluded.stable_since,
            updated_at = excluded.updated_at
        """,
        (run_id, state.effective_concurrency, state.stable_since.isoformat(), now.isoformat()),
    )


__all__ = ["read_state", "write_state"]
