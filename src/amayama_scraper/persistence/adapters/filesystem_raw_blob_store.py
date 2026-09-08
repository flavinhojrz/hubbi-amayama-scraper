"""FilesystemRawBlobStore — satisfaz o port RawBlobStore (T029) usando blob_store.py (T166).

research.md §18; contracts/ports-contract.md.

005 hardening (post-review, HIGH — concorrência entre workers/processos):
`get_or_create()` trata colisão de PK (`content_hash`) como idempotência —
`INSERT ... ON CONFLICT DO NOTHING` seguido de releitura garante que dois
workers persistindo o MESMO hash ao mesmo tempo nunca levantam
`IntegrityError`, e ambos enxergam a MESMA linha vencedora (mesmo
`first_seen_at`) em vez de dois `RawBlob` com timestamps divergentes para o
mesmo conteúdo.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from amayama_scraper.ingestion.raw_blob import RawBlob
from amayama_scraper.persistence.blob_store import blob_path, read_blob, write_blob


def _row_to_raw_blob(row: sqlite3.Row) -> RawBlob:
    return RawBlob(
        content_hash=row["content_hash"],
        size_bytes=row["size_bytes"],
        storage_path=row["storage_path"],
        first_seen_at=datetime.fromisoformat(row["first_seen_at"]),
    )


class FilesystemRawBlobStore:
    def __init__(self, root: Path, conn: sqlite3.Connection) -> None:
        self._root = root
        self._conn = conn

    def get_or_create(self, content_hash: str, raw_content: bytes) -> RawBlob:
        row = self._conn.execute(
            "SELECT * FROM raw_blob WHERE content_hash = ?", (content_hash,)
        ).fetchone()
        if row is not None:
            return _row_to_raw_blob(row)

        # write_blob() já é seguro sob concorrência (tmp exclusivo por
        # chamada + replace() atômico, blob_store.py) — nunca corrompe nem
        # sobrescreve um blob válido com conteúdo diferente (mesmo
        # content_hash implica mesmo conteúdo).
        write_blob(self._root, content_hash, raw_content)
        storage_path = str(blob_path(self._root, content_hash))
        first_seen_at = datetime.now(UTC)
        self._conn.execute(
            """
            INSERT INTO raw_blob (content_hash, size_bytes, storage_path, first_seen_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (content_hash) DO NOTHING
            """,
            (content_hash, len(raw_content), storage_path, first_seen_at.isoformat()),
        )
        # Releitura: se outro worker venceu a corrida do INSERT, esta
        # leitura retorna a linha DELE (mesmo content_hash — mesmo dado
        # logicamente), nunca duas verdades diferentes para o mesmo blob.
        row = self._conn.execute(
            "SELECT * FROM raw_blob WHERE content_hash = ?", (content_hash,)
        ).fetchone()
        assert row is not None  # o INSERT (nosso ou de um concorrente) garante que existe agora
        return _row_to_raw_blob(row)

    def read(self, content_hash: str) -> bytes:
        return read_blob(self._root, content_hash)
