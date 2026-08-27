"""T167 — blob_store é idempotente: escrever o mesmo conteúdo 2x não duplica arquivo físico."""

import hashlib
from pathlib import Path

import pytest

from amayama_scraper.persistence.blob_store import blob_path, read_blob, write_blob


def _hash_of(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def test_write_then_read_round_trips(tmp_path: Path):
    content = b"<html>hello</html>"
    content_hash = _hash_of(content)
    write_blob(tmp_path, content_hash, content)
    assert read_blob(tmp_path, content_hash) == content


def test_writing_the_same_content_twice_does_not_duplicate(tmp_path: Path):
    content = b"same content"
    content_hash = _hash_of(content)
    write_blob(tmp_path, content_hash, content)
    write_blob(tmp_path, content_hash, content)

    path = blob_path(tmp_path, content_hash)
    # exactly one file at the expected sharded path — no "-1"/duplicate siblings
    assert list(path.parent.iterdir()) == [path]


def test_two_level_sharding_by_hash_prefix(tmp_path: Path):
    content_hash = "ab" + "cd" + "e" * 60
    path = blob_path(tmp_path, content_hash)
    assert path == tmp_path / "ab" / "cd" / content_hash


def test_reading_a_missing_blob_raises():
    with pytest.raises(FileNotFoundError):
        read_blob(Path("/nonexistent-root"), "x" * 64)
