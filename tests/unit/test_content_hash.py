"""T051 — content_hash() determinism (data-model.md §4a)."""

import hashlib

from amayama_scraper.ingestion.hashing import content_hash


def test_deterministic():
    data = b"<html>hello</html>"
    assert content_hash(data) == content_hash(data)


def test_matches_stdlib_sha256():
    data = b"some raw html"
    assert content_hash(data) == hashlib.sha256(data).hexdigest()


def test_different_content_different_hash():
    assert content_hash(b"a") != content_hash(b"b")
