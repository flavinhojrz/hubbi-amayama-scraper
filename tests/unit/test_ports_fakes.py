"""T030 — in-memory fakes for the ports (contracts/ports-contract.md).

T009 — FakeBrowserTransport (contracts/browser-transport-contract.md §1),
o único ponto de substituição necessário para testar o driver/orquestração
100% offline, sem Chrome/Selenium real.
"""

import hashlib
import uuid
from datetime import UTC, datetime

import pytest
from tests.unit.fakes import (
    FakeBrowserTransport,
    InMemoryRawBlobStore,
    InMemoryRawCaptureRepository,
)

from amayama_scraper.ingestion.capture_kind import CaptureKind
from amayama_scraper.ingestion.ports import reconstruct_raw_content
from amayama_scraper.ingestion.raw_capture import RawCapture
from amayama_scraper.transport.errors import ChromeNotReachableError
from amayama_scraper.transport.port import BrowserCapture


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


def _capture(url: str) -> BrowserCapture:
    return BrowserCapture(
        page_source=f"<html>{url}</html>", effective_url=url, captured_at=datetime.now(UTC)
    )


def test_fake_browser_transport_navigate_returns_queued_capture():
    transport = FakeBrowserTransport()
    transport.queue_navigate(_capture("https://x/1"))
    result = transport.navigate("https://x/1")
    assert result.effective_url == "https://x/1"
    assert transport.navigate_calls == ["https://x/1"]


def test_fake_browser_transport_navigate_raises_queued_exception():
    transport = FakeBrowserTransport()
    transport.queue_navigate(ChromeNotReachableError("lost"))
    with pytest.raises(ChromeNotReachableError):
        transport.navigate("https://x/1")


def test_fake_browser_transport_current_capture_without_new_navigation():
    transport = FakeBrowserTransport()
    transport.queue_navigate(_capture("https://x/1"))
    transport.navigate("https://x/1")
    # current_capture() re-reads without issuing a new navigation.
    reread = transport.current_capture()
    assert reread.effective_url == "https://x/1"
    assert transport.navigate_calls == ["https://x/1"]  # unchanged — no new navigate() call
    assert transport.current_capture_calls == 1


def test_fake_browser_transport_current_capture_can_be_scripted_independently():
    """Used to simulate a challenge poll loop: several current_capture() reads
    return challenge pages, then a valid one, without any new navigate()."""
    transport = FakeBrowserTransport()
    transport.queue_navigate(_capture("https://x/challenge"))
    transport.navigate("https://x/challenge")
    transport.queue_current_capture(_capture("https://x/still-challenge"))
    transport.queue_current_capture(_capture("https://x/resolved"))

    first_poll = transport.current_capture()
    second_poll = transport.current_capture()
    assert first_poll.effective_url == "https://x/still-challenge"
    assert second_poll.effective_url == "https://x/resolved"
