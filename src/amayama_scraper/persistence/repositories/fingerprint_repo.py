"""fingerprint_repo — data-model.md §7 (FingerprintSet), colunas de spec_snapshot (0006).

`FingerprintSet` não tem tabela própria — vive nas colunas adicionadas por
`0006_fingerprints.sql` ao `spec_snapshot` já criado por `0005_snapshot.sql`
(ownership US3 sobre um subconjunto de colunas de uma tabela cuja
ownership geral é US6). Este módulo expõe leitura/escrita focadas
especificamente no `FingerprintSet`, sem expor o resto do snapshot.
"""

from __future__ import annotations

import sqlite3

from amayama_scraper.fingerprints.types import FingerprintSet


def get_fingerprint_set(conn: sqlite3.Connection, snapshot_id: str) -> FingerprintSet | None:
    row = conn.execute(
        """
        SELECT structure_hash, spec_parts_hash, schema_semantic_hash, image_hash,
               fingerprint_version
        FROM spec_snapshot WHERE snapshot_id = ?
        """,
        (snapshot_id,),
    ).fetchone()
    if row is None or row["fingerprint_version"] is None:
        return None
    return FingerprintSet(
        structure_hash=row["structure_hash"],
        spec_parts_hash=row["spec_parts_hash"],
        schema_semantic_hash=row["schema_semantic_hash"],
        image_hash=row["image_hash"],
        fingerprint_version=row["fingerprint_version"],
    )


def update_fingerprint_set(
    conn: sqlite3.Connection, snapshot_id: str, fingerprints: FingerprintSet
) -> None:
    conn.execute(
        """
        UPDATE spec_snapshot SET
            structure_hash = ?, spec_parts_hash = ?, schema_semantic_hash = ?,
            image_hash = ?, fingerprint_version = ?
        WHERE snapshot_id = ?
        """,
        (
            fingerprints.structure_hash,
            fingerprints.spec_parts_hash,
            fingerprints.schema_semantic_hash,
            fingerprints.image_hash,
            fingerprints.fingerprint_version,
            snapshot_id,
        ),
    )
