"""FilesystemRawBlobStore — satisfaz o port RawBlobStore (T029) usando blob_store.py (T166).

research.md §18; contracts/ports-contract.md.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from amayama_scraper.ingestion.raw_blob import RawBlob
from amayama_scraper.persistence.blob_store import blob_path, read_blob, write_blob


class FilesystemRawBlobStore:
    def __init__(self, root: Path, conn: sqlite3.Connection) -> None:
        self._root = root
        self._conn = conn

    def get_or_create(self, content_hash: str, raw_content: bytes) -> RawBlob:
        row = self._conn.execute(
            "SELECT * FROM raw_blob WHERE content_hash = ?", (content_hash,)
        ).fetchone()
        if row is not None:
            return RawBlob(
                content_hash=row["content_hash"],
                size_bytes=row["size_bytes"],
                storage_path=row["storage_path"],
                first_seen_at=datetime.fromisoformat(row["first_seen_at"]),
            )

        write_blob(self._root, content_hash, raw_content)
        storage_path = str(blob_path(self._root, content_hash))
        first_seen_at = datetime.now(UTC)
        self._conn.execute(
            """
            INSERT INTO raw_blob (content_hash, size_bytes, storage_path, first_seen_at)
            VALUES (?, ?, ?, ?)
            """,
            (content_hash, len(raw_content), storage_path, first_seen_at.isoformat()),
        )
        return RawBlob(
            content_hash=content_hash,
            size_bytes=len(raw_content),
            storage_path=storage_path,
            first_seen_at=first_seen_at,
        )

    def read(self, content_hash: str) -> bytes:
        return read_blob(self._root, content_hash)
