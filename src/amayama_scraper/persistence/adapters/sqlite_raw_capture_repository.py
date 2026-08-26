"""SqliteRawCaptureRepository — satisfaz o port RawCaptureRepository (T029).

contracts/ports-contract.md. `save()` sempre insere uma nova observação —
nunca upsert/merge por content_hash (RawBlob != RawCapture, data-model.md
§4a/§4b).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from amayama_scraper.domain.identity import ExpectedIdentityContext
from amayama_scraper.ingestion.capture_kind import AcquisitionMode, CaptureKind
from amayama_scraper.ingestion.raw_capture import RawCapture


def _expected_identity_context_to_json(ctx: ExpectedIdentityContext | None) -> str | None:
    if ctx is None:
        return None
    return json.dumps(
        {
            "market": ctx.market,
            "model_code": ctx.model_code,
            "amayama_catalog_id": ctx.amayama_catalog_id,
        }
    )


def _expected_identity_context_from_json(raw: str | None) -> ExpectedIdentityContext | None:
    if raw is None:
        return None
    data = json.loads(raw)
    return ExpectedIdentityContext(**data)


class SqliteRawCaptureRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def save(self, capture: RawCapture) -> None:
        self._conn.execute(
            """
            INSERT INTO raw_capture (
                capture_id, run_id, content_hash, source_url, collected_at,
                capture_kind, acquisition_mode, expected_identity_context_json,
                collection_metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                capture.capture_id,
                capture.run_id,
                capture.content_hash,
                capture.source_url,
                capture.collected_at.isoformat(),
                capture.capture_kind.value,
                capture.acquisition_mode.value,
                _expected_identity_context_to_json(capture.expected_identity_context),
                json.dumps(capture.collection_metadata),
            ),
        )

    def get(self, capture_id: str) -> RawCapture | None:
        row = self._conn.execute(
            "SELECT * FROM raw_capture WHERE capture_id = ?", (capture_id,)
        ).fetchone()
        if row is None:
            return None
        return RawCapture(
            capture_id=row["capture_id"],
            run_id=row["run_id"],
            content_hash=row["content_hash"],
            source_url=row["source_url"],
            collected_at=datetime.fromisoformat(row["collected_at"]),
            capture_kind=CaptureKind(row["capture_kind"]),
            acquisition_mode=AcquisitionMode(row["acquisition_mode"]),
            expected_identity_context=_expected_identity_context_from_json(
                row["expected_identity_context_json"]
            ),
            collection_metadata=json.loads(row["collection_metadata_json"]),
        )
