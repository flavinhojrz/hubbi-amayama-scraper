"""spec_category_visit — progresso retomável da visita a UMA categoria declarada.

Bug fix (manifest truncado, ver parsing/spec_group_manifest.py): espelha
deliberadamente o formato/máquina de estados de `checkpoint_repo.py`
(mesmo `CheckpointEntry`/`CheckpointEvent`/`transition()` puro de
`checkpoint/checkpoint_entry.py` — nenhuma nova lógica de estado), mas em
tabela PRÓPRIA (`spec_category_visit`, migration 0010) — nunca em
`checkpoint_entry`. Motivo: `checkpoint_repo.list_accepted()` alimenta
diretamente `snapshots/finalize.py::plan_finalization()`, que trata toda
linha ACCEPTED como um GROUP_DETAIL e chama `parse_group_detail()` sobre o
seu `raw_capture_id` — uma visita de categoria misturada ali seria
interpretada como um grupo real e corromperia a finalização.

`CheckpointEntry.group_id` é reaproveitado apenas para satisfazer o formato
do dataclass (que exige um `group_id` não-vazio) — a tabela não tem coluna
`group_id`; toda linha usa o `CATEGORY_VISIT_GROUP_ID` sentinel abaixo, que
nunca é persistido, apenas preenchido em memória na leitura.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime

from amayama_scraper.checkpoint.checkpoint_entry import (
    CheckpointEntry,
    CheckpointEvent,
    CheckpointStatus,
    transition,
)

#: Preenche `CheckpointEntry.group_id` (exigido não-vazio pelo dataclass) —
#: nunca persistido; `spec_category_visit` não tem coluna `group_id`.
CATEGORY_VISIT_GROUP_ID = "__spec_category_manifest__"


def _row_to_entry(row: sqlite3.Row) -> CheckpointEntry:
    return CheckpointEntry(
        run_id=row["run_id"],
        spec_key=row["spec_key"],
        category_slug=row["category_slug"],
        group_id=CATEGORY_VISIT_GROUP_ID,
        status=CheckpointStatus(row["status"]),
        raw_capture_id=row["raw_capture_id"],
        attempt_count=row["attempt_count"],
        last_attempt_at=(
            datetime.fromisoformat(row["last_attempt_at"]) if row["last_attempt_at"] else None
        ),
        completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
        evidence=json.loads(row["evidence_json"]),
    )


def get_category_visit(
    conn: sqlite3.Connection, run_id: str, spec_key: str, category_slug: str
) -> CheckpointEntry | None:
    row = conn.execute(
        """
        SELECT * FROM spec_category_visit
        WHERE run_id = ? AND spec_key = ? AND category_slug = ?
        """,
        (run_id, spec_key, category_slug),
    ).fetchone()
    return _row_to_entry(row) if row is not None else None


def _upsert_entry(conn: sqlite3.Connection, entry: CheckpointEntry) -> None:
    conn.execute(
        """
        INSERT INTO spec_category_visit (
            run_id, spec_key, category_slug, status, raw_capture_id,
            attempt_count, last_attempt_at, completed_at, evidence_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (run_id, spec_key, category_slug) DO UPDATE SET
            status = excluded.status,
            raw_capture_id = excluded.raw_capture_id,
            attempt_count = excluded.attempt_count,
            last_attempt_at = excluded.last_attempt_at,
            completed_at = excluded.completed_at,
            evidence_json = excluded.evidence_json
        WHERE spec_category_visit.status != 'ACCEPTED'
        """,
        (
            entry.run_id,
            entry.spec_key,
            entry.category_slug,
            entry.status.value,
            entry.raw_capture_id,
            entry.attempt_count,
            entry.last_attempt_at.isoformat() if entry.last_attempt_at else None,
            entry.completed_at.isoformat() if entry.completed_at else None,
            json.dumps(entry.evidence),
        ),
    )


def upsert_category_visit(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    spec_key: str,
    category_slug: str,
    event: CheckpointEvent,
    raw_capture_id: str | None = None,
    evidence: dict[str, object] | None = None,
) -> CheckpointEntry:
    """Same START_ATTEMPT/ACCEPT/REJECT orchestration as `checkpoint/upsert.py`
    ::upsert_checkpoint(), against `spec_category_visit` instead of
    `checkpoint_entry` — see module docstring for why they must stay separate.
    """
    current = get_category_visit(conn, run_id, spec_key, category_slug)
    current_status = current.status if current is not None else CheckpointStatus.PENDING
    attempt_count = current.attempt_count if current is not None else 0
    new_status = transition(current_status, event)
    now = datetime.now(UTC)

    is_start = event is CheckpointEvent.START_ATTEMPT
    is_accept = event is CheckpointEvent.ACCEPT

    entry = CheckpointEntry(
        run_id=run_id,
        spec_key=spec_key,
        category_slug=category_slug,
        group_id=CATEGORY_VISIT_GROUP_ID,
        status=new_status,
        raw_capture_id=(
            raw_capture_id if is_accept else (current.raw_capture_id if current else None)
        ),
        attempt_count=attempt_count + 1 if is_start else attempt_count,
        last_attempt_at=now if is_start else (current.last_attempt_at if current else None),
        completed_at=now if is_accept else (current.completed_at if current else None),
        evidence=evidence if evidence is not None else (current.evidence if current else {}),
    )
    _upsert_entry(conn, entry)
    return entry
