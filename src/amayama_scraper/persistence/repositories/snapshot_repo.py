"""snapshot_repo — data-model.md §6, §13b (idempotência por idempotency_key).

`save()` é insert-or-get: mesmo `idempotency_key` nunca insere uma segunda
linha — retorna o `snapshot_id` já existente em vez de duplicar (fase 2 de
`finalize_spec_entry()`, data-model.md §13c).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from amayama_scraper.snapshots.snapshot import SnapshotState, SpecSnapshot


def save_snapshot(conn: sqlite3.Connection, snapshot: SpecSnapshot) -> str:
    existing = conn.execute(
        "SELECT snapshot_id FROM spec_snapshot WHERE idempotency_key = ?",
        (snapshot.idempotency_key,),
    ).fetchone()
    if existing is not None:
        return str(existing["snapshot_id"])

    conn.execute(
        """
        INSERT INTO spec_snapshot (
            snapshot_id, spec_identity_ref, idempotency_key, collected_at,
            parser_version, normalizer_version, collection_complete, state,
            counts_json, fingerprint_version, structure_hash, spec_parts_hash,
            schema_semantic_hash, image_hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            snapshot.snapshot_id,
            snapshot.spec_identity_ref,
            snapshot.idempotency_key,
            snapshot.collected_at.isoformat(),
            snapshot.parser_version,
            snapshot.normalizer_version,
            int(snapshot.collection_complete),
            snapshot.state.value,
            json.dumps(snapshot.counts),
            snapshot.fingerprint_version,
            snapshot.structure_hash,
            snapshot.spec_parts_hash,
            snapshot.schema_semantic_hash,
            snapshot.image_hash,
        ),
    )
    return snapshot.snapshot_id


def _row_to_snapshot(row: sqlite3.Row) -> SpecSnapshot:
    return SpecSnapshot(
        snapshot_id=row["snapshot_id"],
        spec_identity_ref=row["spec_identity_ref"],
        idempotency_key=row["idempotency_key"],
        collected_at=datetime.fromisoformat(row["collected_at"]),
        parser_version=row["parser_version"],
        normalizer_version=row["normalizer_version"],
        fingerprint_version=row["fingerprint_version"],
        collection_complete=bool(row["collection_complete"]),
        structure_hash=row["structure_hash"],
        spec_parts_hash=row["spec_parts_hash"],
        schema_semantic_hash=row["schema_semantic_hash"],
        image_hash=row["image_hash"],
        state=SnapshotState(row["state"]),
        counts=json.loads(row["counts_json"]),
    )


def get_snapshot(conn: sqlite3.Connection, snapshot_id: str) -> SpecSnapshot | None:
    row = conn.execute(
        "SELECT * FROM spec_snapshot WHERE snapshot_id = ?", (snapshot_id,)
    ).fetchone()
    return _row_to_snapshot(row) if row is not None else None


def get_by_idempotency_key(conn: sqlite3.Connection, idempotency_key: str) -> SpecSnapshot | None:
    row = conn.execute(
        "SELECT * FROM spec_snapshot WHERE idempotency_key = ?", (idempotency_key,)
    ).fetchone()
    return _row_to_snapshot(row) if row is not None else None


def supersede(conn: sqlite3.Connection, snapshot_id: str) -> None:
    conn.execute(
        "UPDATE spec_snapshot SET state = ? WHERE snapshot_id = ?",
        (SnapshotState.SUPERSEDED.value, snapshot_id),
    )
