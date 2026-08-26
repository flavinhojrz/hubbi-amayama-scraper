"""RawBlob — conteúdo físico, content-addressed (data-model.md §4a).

Deduplica bytes físicos. Não carrega provenance de coleta — isso é
responsabilidade exclusiva de RawCapture (§4b).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class RawBlob:
    content_hash: str
    size_bytes: int
    storage_path: str
    first_seen_at: datetime

    def __post_init__(self) -> None:
        if not self.content_hash or len(self.content_hash) != 64:
            raise ValueError("RawBlob.content_hash must be a sha256 hex digest (64 chars)")
        if self.size_bytes < 0:
            raise ValueError("RawBlob.size_bytes must not be negative")
        if not self.storage_path or not self.storage_path.strip():
            raise ValueError("RawBlob.storage_path must not be empty")
