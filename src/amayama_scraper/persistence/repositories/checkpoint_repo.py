"""collection_run_repo + checkpoint_entry upsert/list_accepted — data-model.md §11, §13a.

Upsert sobre `UNIQUE(run_id, spec_key, category_slug, group_id)`: chamar
duas vezes nunca duplica linha. `ACCEPTED` é terminal (`transition()`,
checkpoint/checkpoint_entry.py) — o upsert aqui apenas persiste o status já
decidido pela transição pura, não reimplementa a máquina de estados.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from amayama_scraper.checkpoint.checkpoint_entry import CheckpointEntry, CheckpointStatus
from amayama_scraper.checkpoint.collection_run import CollectionRun


def save_collection_run(conn: sqlite3.Connection, run: CollectionRun) -> None:
    conn.execute(
        """
        INSERT INTO collection_run (run_id, scope, started_at, resumed_at, completed_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (run_id) DO UPDATE SET
            resumed_at = excluded.resumed_at,
            completed_at = excluded.completed_at
        """,
        (
            run.run_id,
            run.scope,
            run.started_at.isoformat() if run.started_at else None,
            run.resumed_at.isoformat() if run.resumed_at else None,
            run.completed_at.isoformat() if run.completed_at else None,
        ),
    )


def list_incomplete_runs(conn: sqlite3.Connection, scope: str) -> list[CollectionRun]:
    """CollectionRun com scope == scope e completed_at IS NULL, mais antigo primeiro.

    T026/T027 (002) — data-model.md §7, DEC-005. Leitura aditiva sobre a
    tabela collection_run já existente — nenhuma migration. Note que este
    construtor de linha não usa `CollectionRun(...)` diretamente para
    permitir refletir corretamente uma linha de escopo estrangeiro que só
    pode existir via SQL direto (CollectionRun.__post_init__ recusaria
    construí-la em Python) — o filtro `WHERE scope = ?` já a exclui do
    resultado antes disso ser relevante.
    """
    rows = conn.execute(
        "SELECT * FROM collection_run WHERE scope = ? AND completed_at IS NULL ORDER BY started_at",
        (scope,),
    ).fetchall()
    return [
        CollectionRun(
            run_id=row["run_id"],
            scope=row["scope"],
            started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
            resumed_at=datetime.fromisoformat(row["resumed_at"]) if row["resumed_at"] else None,
            completed_at=None,
        )
        for row in rows
    ]


def get_collection_run(conn: sqlite3.Connection, run_id: str) -> CollectionRun | None:
    row = conn.execute("SELECT * FROM collection_run WHERE run_id = ?", (run_id,)).fetchone()
    if row is None:
        return None
    return CollectionRun(
        run_id=row["run_id"],
        scope=row["scope"],
        started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
        resumed_at=datetime.fromisoformat(row["resumed_at"]) if row["resumed_at"] else None,
        completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
    )


def upsert_checkpoint_entry(conn: sqlite3.Connection, entry: CheckpointEntry) -> None:
    conn.execute(
        """
        INSERT INTO checkpoint_entry (
            run_id, spec_key, category_slug, group_id, status, raw_capture_id,
            attempt_count, last_attempt_at, completed_at, evidence_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (run_id, spec_key, category_slug, group_id) DO UPDATE SET
            status = excluded.status,
            raw_capture_id = excluded.raw_capture_id,
            attempt_count = excluded.attempt_count,
            last_attempt_at = excluded.last_attempt_at,
            completed_at = excluded.completed_at,
            evidence_json = excluded.evidence_json
        WHERE checkpoint_entry.status != 'ACCEPTED'
        """,
        (
            entry.run_id,
            entry.spec_key,
            entry.category_slug,
            entry.group_id,
            entry.status.value,
            entry.raw_capture_id,
            entry.attempt_count,
            entry.last_attempt_at.isoformat() if entry.last_attempt_at else None,
            entry.completed_at.isoformat() if entry.completed_at else None,
            json.dumps(entry.evidence),
        ),
    )


def _row_to_checkpoint_entry(row: sqlite3.Row) -> CheckpointEntry:
    return CheckpointEntry(
        run_id=row["run_id"],
        spec_key=row["spec_key"],
        category_slug=row["category_slug"],
        group_id=row["group_id"],
        status=CheckpointStatus(row["status"]),
        raw_capture_id=row["raw_capture_id"],
        attempt_count=row["attempt_count"],
        last_attempt_at=(
            datetime.fromisoformat(row["last_attempt_at"]) if row["last_attempt_at"] else None
        ),
        completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
        evidence=json.loads(row["evidence_json"]),
    )


def get_checkpoint_entry(
    conn: sqlite3.Connection, run_id: str, spec_key: str, category_slug: str, group_id: str
) -> CheckpointEntry | None:
    row = conn.execute(
        """
        SELECT * FROM checkpoint_entry
        WHERE run_id = ? AND spec_key = ? AND category_slug = ? AND group_id = ?
        """,
        (run_id, spec_key, category_slug, group_id),
    ).fetchone()
    return _row_to_checkpoint_entry(row) if row is not None else None


def list_accepted(conn: sqlite3.Connection, run_id: str, spec_key: str) -> list[CheckpointEntry]:
    rows = conn.execute(
        """
        SELECT * FROM checkpoint_entry
        WHERE run_id = ? AND spec_key = ? AND status = 'ACCEPTED'
        ORDER BY category_slug, group_id
        """,
        (run_id, spec_key),
    ).fetchall()
    return [_row_to_checkpoint_entry(row) for row in rows]
