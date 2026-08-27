"""content_hash() — SHA-256 do raw_content (data-model.md §4a)."""

from __future__ import annotations

import hashlib


def content_hash(raw_content: bytes) -> str:
    return hashlib.sha256(raw_content).hexdigest()
