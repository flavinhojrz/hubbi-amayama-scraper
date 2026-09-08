"""spec_pool_disposition_repo.py — disposição de elegibilidade de claim por
spec (005 hardening, BLOCKER 2 — 2ª rodada; data-model: `spec_pool_disposition`).

Substitui o mecanismo anterior de backoff temporal (removido —
`lease_repo.apply_backoff()` não existe mais) por uma disposição explícita,
persistida, chaveada por `(run_id, spec_key)`:

- `MANUAL_RETRY_REQUIRED`: nunca reelegível em execução normal (mesmo depois
  de tempo, mesmo numa nova invocação de `run_pool()`) — só
  `--retry-rejected` reabre.
- `DEFERRED_THIS_SESSION`: inelegível apenas para o `pool_session_id` que a
  produziu — uma nova invocação de `run_pool()` (`--resume`) gera um
  `pool_session_id` novo e pode tentar de novo.

`clear()` remove a disposição (progresso real supera qualquer disposição
anterior) — não é dado de auditoria (`checkpoint_entry`/`spec_snapshot`
continuam a fonte de verdade de progresso, Constitution §4), apenas
coordenação de elegibilidade.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class SpecPoolDisposition:
    state: str  # "MANUAL_RETRY_REQUIRED" | "DEFERRED_THIS_SESSION"
    pool_session_id: str | None


def get(conn: sqlite3.Connection, *, run_id: str, spec_key: str) -> SpecPoolDisposition | None:
    row = conn.execute(
        "SELECT state, pool_session_id FROM spec_pool_disposition "
        "WHERE run_id = ? AND spec_key = ?",
        (run_id, spec_key),
    ).fetchone()
    if row is None:
        return None
    return SpecPoolDisposition(state=row["state"], pool_session_id=row["pool_session_id"])


def set_manual_retry_required(
    conn: sqlite3.Connection, *, run_id: str, spec_key: str, now: datetime
) -> None:
    """FR (BLOCKER 2): unidades `GROUP_REJECTED_AWAITING_MANUAL_RETRY` (ou
    qualquer condição cujo retry normal não seja permitido) — a spec fica
    inelegível até `--retry-rejected` autorizar explicitamente, mesmo depois
    de tempo ou de uma nova invocação do pool."""
    conn.execute(
        """
        INSERT INTO spec_pool_disposition (run_id, spec_key, state, pool_session_id, updated_at)
        VALUES (?, ?, 'MANUAL_RETRY_REQUIRED', NULL, ?)
        ON CONFLICT (run_id, spec_key) DO UPDATE SET
            state = excluded.state,
            pool_session_id = excluded.pool_session_id,
            updated_at = excluded.updated_at
        """,
        (run_id, spec_key, now.isoformat()),
    )


def set_deferred_this_session(
    conn: sqlite3.Connection, *, run_id: str, spec_key: str, pool_session_id: str, now: datetime
) -> None:
    """FR (BLOCKER 2): falha transitória sem progresso (challenge timeout,
    navegação rejeitada) — inelegível só para `pool_session_id`; uma nova
    invocação de `run_pool()` (outro `pool_session_id`) pode tentar de novo."""
    conn.execute(
        """
        INSERT INTO spec_pool_disposition (run_id, spec_key, state, pool_session_id, updated_at)
        VALUES (?, ?, 'DEFERRED_THIS_SESSION', ?, ?)
        ON CONFLICT (run_id, spec_key) DO UPDATE SET
            state = excluded.state,
            pool_session_id = excluded.pool_session_id,
            updated_at = excluded.updated_at
        """,
        (run_id, spec_key, pool_session_id, now.isoformat()),
    )


def clear(conn: sqlite3.Connection, *, run_id: str, spec_key: str) -> None:
    """Progresso real (`SpecPassDisposition.PROGRESSED`) supera qualquer
    disposição anterior — a spec volta a ser avaliada normalmente pelas
    regras usuais (`current_state`/`checkpoint_entry`), sem nenhum resquício
    de uma disposição de uma passagem anterior."""
    conn.execute(
        "DELETE FROM spec_pool_disposition WHERE run_id = ? AND spec_key = ?", (run_id, spec_key)
    )


__all__ = [
    "SpecPoolDisposition",
    "clear",
    "get",
    "set_deferred_this_session",
    "set_manual_retry_required",
]
