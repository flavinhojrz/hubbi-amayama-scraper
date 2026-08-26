"""Ports de persistência (Dependency Inversion) — contracts/ports-contract.md.

O núcleo de ingestão depende destas abstrações, nunca de SQLite/filesystem
concretos. Phase 10 implementa os adapters concretos que as satisfazem;
testes usam fakes em memória (tests/unit/fakes.py). Também são o que
permite reconstruir (replay) o conteúdo bruto de um Group ACCEPTED
inteiramente a partir do que está persistido (research.md §18).
"""

from __future__ import annotations

from typing import Protocol

from amayama_scraper.ingestion.raw_blob import RawBlob
from amayama_scraper.ingestion.raw_capture import RawCapture


class RawBlobStore(Protocol):
    def get_or_create(self, content_hash: str, raw_content: bytes) -> RawBlob:
        """Retorna o RawBlob existente para content_hash, ou grava um novo."""
        ...

    def read(self, content_hash: str) -> bytes:
        """Lê o conteúdo bruto de um RawBlob já existente."""
        ...


class RawCaptureRepository(Protocol):
    def save(self, capture: RawCapture) -> None:
        """Sempre insere uma nova observação — nunca faz upsert/merge por content_hash."""
        ...

    def get(self, capture_id: str) -> RawCapture | None: ...


def reconstruct_raw_content(
    capture_id: str,
    capture_repo: RawCaptureRepository,
    blob_store: RawBlobStore,
) -> bytes:
    """RawCapture -> RawBlob -> raw bytes (contracts/ports-contract.md "Replay").

    Suficiente para reconstruir o conteúdo bruto de qualquer Group já
    ACCEPTED sem depender de nenhum objeto parseado ter sobrevivido em
    memória entre processos.
    """
    raw_capture = capture_repo.get(capture_id)
    if raw_capture is None:
        raise LookupError(f"RawCapture not found for capture_id={capture_id!r}")
    return blob_store.read(raw_capture.content_hash)
