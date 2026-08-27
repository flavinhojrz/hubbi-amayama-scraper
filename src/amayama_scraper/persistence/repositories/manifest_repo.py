"""manifest_repo — data-model.md §15 (SpecGroupManifest, autoridade).

`get_authoritative()` aplica as 4 condições de autoridade. Condição 1
("captura de origem ACCEPTED") é estruturalmente garantida pelo pipeline —
um `SpecGroupManifest` só é produzido por `parse_spec_group_manifest()`
quando a captura já foi roteada como `ACCEPTED` (T093, invariante "somente
ACCEPTED segue para parsing") — nunca é reverificada aqui. Condições 2/4
(sem `critical_error`/duplicata) já são garantidas na construção do
`SpecGroupManifest` (`ManifestCategory` levanta `DuplicateGroupIdError`).
Esta função verifica a condição restante, genuinamente dependente de
estado persistido: 3 (`manifest_complete`).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from amayama_scraper.domain.manifest import (
    ManifestCategory,
    ManifestGroupRef,
    SpecGroupManifest,
    is_manifest_authoritative,
)


def _categories_to_json(manifest: SpecGroupManifest) -> str:
    return json.dumps(
        [
            {
                "category_slug": category.category_slug,
                "groups": [
                    {"group_id": g.group_id, "source_url": g.source_url} for g in category.groups
                ],
            }
            for category in manifest.categories
        ]
    )


def _categories_from_json(raw: str) -> tuple[ManifestCategory, ...]:
    data = json.loads(raw)
    return tuple(
        ManifestCategory(
            category_slug=cat["category_slug"],
            groups=tuple(
                ManifestGroupRef(group_id=g["group_id"], source_url=g["source_url"])
                for g in cat["groups"]
            ),
        )
        for cat in data
    )


def save_manifest(conn: sqlite3.Connection, manifest: SpecGroupManifest, run_id: str) -> int:
    cursor = conn.execute(
        """
        INSERT INTO spec_group_manifest (
            spec_key, run_id, source_capture_id, discovered_at,
            categories_json, manifest_complete, validation_evidence_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            manifest.spec_key,
            run_id,
            manifest.source_capture_id,
            manifest.discovered_at.isoformat(),
            _categories_to_json(manifest),
            int(manifest.manifest_complete),
            json.dumps(manifest.validation_evidence),
        ),
    )
    return int(cursor.lastrowid)  # type: ignore[arg-type]


def _row_to_manifest(row: sqlite3.Row) -> SpecGroupManifest:
    return SpecGroupManifest(
        spec_key=row["spec_key"],
        source_capture_id=row["source_capture_id"],
        discovered_at=datetime.fromisoformat(row["discovered_at"]),
        categories=_categories_from_json(row["categories_json"]),
        manifest_complete=bool(row["manifest_complete"]),
        validation_evidence=json.loads(row["validation_evidence_json"]),
    )


def get_authoritative(
    conn: sqlite3.Connection, spec_key: str, run_id: str
) -> SpecGroupManifest | None:
    row = conn.execute(
        """
        SELECT * FROM spec_group_manifest
        WHERE spec_key = ? AND run_id = ?
        ORDER BY id DESC LIMIT 1
        """,
        (spec_key, run_id),
    ).fetchone()
    if row is None:
        return None
    manifest = _row_to_manifest(row)
    return manifest if is_manifest_authoritative(manifest) else None
