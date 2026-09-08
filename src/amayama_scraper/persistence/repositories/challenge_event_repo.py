"""challenge_event_repo.py — log de challenges (005, US3/US4; data-model.md §3).

Fonte única tanto do rate limiter (`count_in_window()`, FR-063) quanto das
métricas de challenge (US4: "challenges", "challenges/hora", "tempo total
esperando challenge") — evita duas tabelas que poderiam divergir sobre "o
que conta como challenge" (contracts/worker-pool-contract.md §4).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta


def record_observed(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    worker_id: str,
    capture_kind: str,
    observed_at: datetime,
    spec_key: str | None = None,
) -> int:
    """FR-051: um challenge observado em qualquer worker alimenta o estado
    global — chamado no mesmo ponto em que `await_challenge_resolution()`
    emite `CHALLENGE_WAITING`. Retorna o `id` da linha, para
    `record_resolved()` fechar o mesmo evento depois."""
    cursor = conn.execute(
        """
        INSERT INTO challenge_event (run_id, worker_id, spec_key, capture_kind, observed_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (run_id, worker_id, spec_key, capture_kind, observed_at.isoformat()),
    )
    return int(cursor.lastrowid)  # type: ignore[arg-type]


def record_resolved(conn: sqlite3.Connection, *, event_id: int, resolved_at: datetime) -> None:
    """Fecha o evento aberto por `record_observed()` — usado tanto em
    `CHALLENGE_RESOLVED` quanto em `CHALLENGE_TIMEOUT` (ambos encerram a
    espera; a métrica "tempo total esperando challenge" soma os dois)."""
    conn.execute(
        "UPDATE challenge_event SET resolved_at = ? WHERE id = ?",
        (resolved_at.isoformat(), event_id),
    )


def count_in_window(
    conn: sqlite3.Connection, *, run_id: str, now: datetime, window_seconds: float
) -> int:
    """FR-063: número de challenges observados dentro dos últimos
    `window_seconds` (a partir de `now`) — a política de decremento do rate
    limiter é aplicada sobre este valor."""
    window_start = (now - timedelta(seconds=window_seconds)).isoformat()
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM challenge_event "
        "WHERE run_id = ? AND observed_at >= ? AND observed_at <= ?",
        (run_id, window_start, now.isoformat()),
    ).fetchone()
    return int(row["n"])


def count_total(conn: sqlite3.Connection, *, run_id: str) -> int:
    """Métrica "challenges" (US4) — total do run inteiro, não apenas a janela."""
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM challenge_event WHERE run_id = ?", (run_id,)
    ).fetchone()
    return int(row["n"])


def count_in_trailing_hour(conn: sqlite3.Connection, *, run_id: str, now: datetime) -> int:
    """Métrica "challenges/hora" (US4)."""
    return count_in_window(conn, run_id=run_id, now=now, window_seconds=3600.0)


def total_wait_seconds(conn: sqlite3.Connection, *, run_id: str) -> float:
    """Métrica "tempo total esperando challenge" (US4) — soma
    `resolved_at - observed_at` de todo evento já fechado; eventos ainda
    abertos (challenge em andamento neste instante) não contam ainda (a
    espera só é somada quando termina, resolvida ou por timeout)."""
    rows = conn.execute(
        "SELECT observed_at, resolved_at FROM challenge_event "
        "WHERE run_id = ? AND resolved_at IS NOT NULL",
        (run_id,),
    ).fetchall()
    total = 0.0
    for row in rows:
        observed = datetime.fromisoformat(row["observed_at"])
        resolved = datetime.fromisoformat(row["resolved_at"])
        total += (resolved - observed).total_seconds()
    return total


__all__ = [
    "count_in_trailing_hour",
    "count_in_window",
    "count_total",
    "record_observed",
    "record_resolved",
    "total_wait_seconds",
]
