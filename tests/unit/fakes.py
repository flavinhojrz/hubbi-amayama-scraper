"""In-memory fakes for the ingestion ports (contracts/ports-contract.md).

Used across the test suite to keep everything above Phase 10 testable
100% offline, independent of SQLite/filesystem.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from amayama_scraper.ingestion.raw_blob import RawBlob
from amayama_scraper.ingestion.raw_capture import RawCapture


@dataclass
class InMemoryRawBlobStore:
    _blobs: dict[str, bytes] = field(default_factory=dict)
    _records: dict[str, RawBlob] = field(default_factory=dict)

    def get_or_create(self, content_hash: str, raw_content: bytes) -> RawBlob:
        existing = self._records.get(content_hash)
        if existing is not None:
            return existing
        record = RawBlob(
            content_hash=content_hash,
            size_bytes=len(raw_content),
            storage_path=f"raw/{content_hash[:2]}/{content_hash}",
            first_seen_at=datetime.now(UTC),
        )
        self._blobs[content_hash] = raw_content
        self._records[content_hash] = record
        return record

    def read(self, content_hash: str) -> bytes:
        try:
            return self._blobs[content_hash]
        except KeyError as exc:
            raise LookupError(f"RawBlob not found for content_hash={content_hash!r}") from exc


@dataclass
class InMemoryRawCaptureRepository:
    _captures: dict[str, RawCapture] = field(default_factory=dict)

    def save(self, capture: RawCapture) -> None:
        # Sempre insere uma nova observação — nunca faz upsert por content_hash.
        self._captures[capture.capture_id] = capture

    def get(self, capture_id: str) -> RawCapture | None:
        return self._captures.get(capture_id)
