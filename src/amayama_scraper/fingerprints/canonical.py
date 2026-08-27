"""Canonical JSON serialization and domain-separated SHA-256 hashing.

Shared by identity (stable_key) and every fingerprint in this package —
same determinism guarantee, same domain-separator + version pattern
throughout (Constitution §8, research.md §7).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(value: Any) -> str:
    """Deterministic JSON serialization: sorted keys, ASCII-escaped, compact."""
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def domain_hash(domain_separator: str, payload: Any) -> str:
    """SHA256(domain_separator + canonical_json(payload)), hex-encoded."""
    data = (domain_separator + canonical_json(payload)).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def multiset_counts(items: list[str]) -> list[tuple[str, int]]:
    """Deterministic (sorted) multiset representation: (value, count) pairs.

    Order-independent, duplicate-sensitive — the representation required
    for hierarchical fingerprint comparison (Constitution §8).
    """
    counts: dict[str, int] = {}
    for item in items:
        counts[item] = counts.get(item, 0) + 1
    return sorted(counts.items())
