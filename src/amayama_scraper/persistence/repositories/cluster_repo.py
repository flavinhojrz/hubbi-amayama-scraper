"""cluster_repo — data-model.md §9 (ClusterAssignment).

`assign()` faz upsert por `spec_identity_ref`: uma spec tem no máximo uma
assignment vigente. Quando `normalizer_version`/`fingerprint_version`
mudam, o upsert sobrescreve a linha anterior — invalidando (T193) a
assignment antiga sem manter histórico, já que `cluster_key` é sempre
recomputável (ponto 14 do PLAN, `equivalence/cluster.py`).
"""

from __future__ import annotations

import sqlite3

from amayama_scraper.equivalence.cluster_types import ClusterAssignment


def assign(conn: sqlite3.Connection, assignment: ClusterAssignment) -> None:
    conn.execute(
        """
        INSERT INTO cluster_assignment (
            spec_identity_ref, cluster_key, normalizer_version, fingerprint_version
        ) VALUES (?, ?, ?, ?)
        ON CONFLICT (spec_identity_ref) DO UPDATE SET
            cluster_key = excluded.cluster_key,
            normalizer_version = excluded.normalizer_version,
            fingerprint_version = excluded.fingerprint_version
        """,
        (
            assignment.spec_identity_ref,
            assignment.cluster_key,
            assignment.normalizer_version,
            assignment.fingerprint_version,
        ),
    )


def get_assignment(conn: sqlite3.Connection, spec_identity_ref: str) -> ClusterAssignment | None:
    row = conn.execute(
        "SELECT * FROM cluster_assignment WHERE spec_identity_ref = ?", (spec_identity_ref,)
    ).fetchone()
    if row is None:
        return None
    return ClusterAssignment(
        spec_identity_ref=row["spec_identity_ref"],
        cluster_key=row["cluster_key"],
        normalizer_version=row["normalizer_version"],
        fingerprint_version=row["fingerprint_version"],
    )


def list_members(conn: sqlite3.Connection, cluster_key: str) -> list[str]:
    rows = conn.execute(
        "SELECT spec_identity_ref FROM cluster_assignment WHERE cluster_key = ? "
        "ORDER BY spec_identity_ref",
        (cluster_key,),
    ).fetchall()
    return [row["spec_identity_ref"] for row in rows]
