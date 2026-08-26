"""current_state_repo — data-model.md §12 (CurrentSpecState, projeção reconstruível).

Nunca é a fonte de verdade — apenas reflete o `SpecSnapshot` `VALID`/`STALE`
mais recente (por `collected_at`) e o `cluster_key` atual
(`cluster_assignment`), ambos já persistidos. `materialize()` recomputa a
projeção inteiramente a partir dessas duas fontes, sempre reconstruível.
"""

from __future__ import annotations

import sqlite3

from amayama_scraper.domain.current_state import CurrentSpecState


def materialize(conn: sqlite3.Connection, spec_identity_ref: str) -> CurrentSpecState | None:
    snapshot_row = conn.execute(
        """
        SELECT snapshot_id FROM spec_snapshot
        WHERE spec_identity_ref = ? AND state IN ('VALID', 'STALE')
        ORDER BY collected_at DESC LIMIT 1
        """,
        (spec_identity_ref,),
    ).fetchone()
    if snapshot_row is None:
        return None

    cluster_row = conn.execute(
        "SELECT cluster_key FROM cluster_assignment WHERE spec_identity_ref = ?",
        (spec_identity_ref,),
    ).fetchone()
    cluster_key = cluster_row["cluster_key"] if cluster_row is not None else None

    state = CurrentSpecState(
        spec_identity_ref=spec_identity_ref,
        latest_snapshot_id=snapshot_row["snapshot_id"],
        cluster_key=cluster_key,
    )
    conn.execute(
        """
        INSERT INTO current_spec_state (spec_identity_ref, latest_snapshot_id, cluster_key)
        VALUES (?, ?, ?)
        ON CONFLICT (spec_identity_ref) DO UPDATE SET
            latest_snapshot_id = excluded.latest_snapshot_id,
            cluster_key = excluded.cluster_key
        """,
        (state.spec_identity_ref, state.latest_snapshot_id, state.cluster_key),
    )
    return state


def get_current_state(conn: sqlite3.Connection, spec_identity_ref: str) -> CurrentSpecState | None:
    row = conn.execute(
        "SELECT * FROM current_spec_state WHERE spec_identity_ref = ?", (spec_identity_ref,)
    ).fetchone()
    if row is None:
        return None
    return CurrentSpecState(
        spec_identity_ref=row["spec_identity_ref"],
        latest_snapshot_id=row["latest_snapshot_id"],
        cluster_key=row["cluster_key"],
    )
