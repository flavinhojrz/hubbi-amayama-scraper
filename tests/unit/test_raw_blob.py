"""T025 — RawBlob immutability and fields (data-model.md §4a)."""

import hashlib
from datetime import UTC, datetime

import pytest

from amayama_scraper.ingestion.raw_blob import RawBlob


def make_blob(**overrides: object) -> RawBlob:
    content_hash = hashlib.sha256(b"hello").hexdigest()
    defaults: dict[str, object] = dict(
        content_hash=content_hash,
        size_bytes=5,
        storage_path=f"raw/{content_hash[:2]}/{content_hash}.html",
        first_seen_at=datetime(2026, 8, 26, tzinfo=UTC),
    )
    defaults.update(overrides)
    return RawBlob(**defaults)  # type: ignore[arg-type]


def test_is_frozen():
    blob = make_blob()
    with pytest.raises(Exception):  # noqa: B017 - dataclasses.FrozenInstanceError
        blob.size_bytes = 999  # type: ignore[misc]


def test_content_hash_must_be_sha256_hex():
    with pytest.raises(ValueError):
        make_blob(content_hash="not-a-hash")


def test_negative_size_rejected():
    with pytest.raises(ValueError):
        make_blob(size_bytes=-1)


def test_fields_roundtrip():
    blob = make_blob(size_bytes=42)
    assert blob.size_bytes == 42
    assert blob.storage_path.endswith(".html")
