"""T030 — in-memory fakes for the ports (contracts/ports-contract.md)."""

import hashlib
import uuid
from datetime import UTC, datetime

from tests.unit.fakes import InMemoryRawBlobStore, InMemoryRawCaptureRepository

from amayama_scraper.ingestion.capture_kind import CaptureKind
from amayama_scraper.ingestion.ports import reconstruct_raw_content
from amayama_scraper.ingestion.raw_capture import RawCapture


def test_get_or_create_is_idempotent_same_content_hash_no_duplicate():
    store = InMemoryRawBlobStore()
    content = b"<html>hello</html>"
    content_hash = hashlib.sha256(content).hexdigest()

    first = store.get_or_create(content_hash, content)
    second = store.get_or_create(content_hash, content)

    assert first == second
    assert len(store._blobs) == 1  # noqa: SLF001 - inspecting fake internals in test


def test_save_always_inserts_new_observation():
    repo = InMemoryRawCaptureRepository()
    content_hash = hashlib.sha256(b"x").hexdigest()
    a = RawCapture(
        capture_id=str(uuid.uuid4()),
        run_id="run-1",
        content_hash=content_hash,
        source_url="https://x/1",
        collected_at=datetime(2026, 8, 26, tzinfo=UTC),
        capture_kind=CaptureKind.GROUP_DETAIL,
    )
    b = RawCapture(
        capture_id=str(uuid.uuid4()),
        run_id="run-2",
        content_hash=content_hash,
        source_url="https://x/1",
        collected_at=datetime(2026, 8, 26, tzinfo=UTC),
        capture_kind=CaptureKind.GROUP_DETAIL,
    )
    repo.save(a)
    repo.save(b)
    assert repo.get(a.capture_id) == a
    assert repo.get(b.capture_id) == b
    assert a.capture_id != b.capture_id


def test_read_round_trip_reconstructs_original_bytes():
    """The write+read pair is what makes replay possible after a restart."""
    store = InMemoryRawBlobStore()
    repo = InMemoryRawCaptureRepository()
    content = b"<html>group detail</html>"
    content_hash = hashlib.sha256(content).hexdigest()
    store.get_or_create(content_hash, content)
    capture = RawCapture(
        capture_id=str(uuid.uuid4()),
        run_id="run-1",
        content_hash=content_hash,
        source_url="https://x/1",
        collected_at=datetime(2026, 8, 26, tzinfo=UTC),
        capture_kind=CaptureKind.GROUP_DETAIL,
    )
    repo.save(capture)

    # Simulate a fresh instance reading only via the ports (no shared state carried over).
    recovered = reconstruct_raw_content(capture.capture_id, repo, store)
    assert recovered == content


def test_get_missing_capture_returns_none():
    repo = InMemoryRawCaptureRepository()
    assert repo.get("does-not-exist") is None
