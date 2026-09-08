"""worker_heartbeat_repo.py — observabilidade de "workers ativos" (005, US4;
data-model.md §4).

Nunca participa de nenhuma decisão de claim/lease (essa responsabilidade é
exclusiva de `lease_repo.py`) — puramente informativo para métricas (US4).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta


def upsert_heartbeat(
    conn: sqlite3.Connection, *, run_id: str, worker_id: str, pid: int, now: datetime
) -> None:
    conn.execute(
        """
        INSERT INTO worker_heartbeat (run_id, worker_id, pid, started_at, last_heartbeat_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (run_id, worker_id) DO UPDATE SET
            last_heartbeat_at = excluded.last_heartbeat_at
        """,
        (run_id, worker_id, pid, now.isoformat(), now.isoformat()),
    )


def count_active(
    conn: sqlite3.Connection, *, run_id: str, now: datetime, staleness_seconds: float
) -> int:
    threshold = (now - timedelta(seconds=staleness_seconds)).isoformat()
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM worker_heartbeat WHERE run_id = ? AND last_heartbeat_at >= ?",
        (run_id, threshold),
    ).fetchone()
    return int(row["n"])


__all__ = ["count_active", "upsert_heartbeat"]
