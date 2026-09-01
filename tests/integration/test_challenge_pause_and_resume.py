"""T052/T056-T058 — await_challenge_resolution() (FR-011, FR-012, SC-005;
contracts/browser-transport-contract.md §4).

Sempre reprocessa via process_capture()/classify_capture() reais a cada
verificação — nunca uma decisão paralela de "resolvido". Cobre challenge
nos três níveis (MARKET_INDEX, SPEC_NAVIGATION, GROUP_DETAIL).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from tests.unit.fakes import (
    FakeBrowserTransport,
    InMemoryRawBlobStore,
    InMemoryRawCaptureRepository,
)

from amayama_scraper.checkpoint.collection_run import CollectionRun
from amayama_scraper.ingestion.capture_kind import CaptureKind
from amayama_scraper.orchestration.collection_driver import await_challenge_resolution
from amayama_scraper.persistence.adapters.filesystem_raw_blob_store import FilesystemRawBlobStore
from amayama_scraper.persistence.adapters.sqlite_raw_capture_repository import (
    SqliteRawCaptureRepository,
)
from amayama_scraper.persistence.db import connect
from amayama_scraper.persistence.migrations.runner import run_migrations
from amayama_scraper.persistence.repositories.checkpoint_repo import (
    get_checkpoint_entry,
    save_collection_run,
)
from amayama_scraper.persistence.repositories.spec_registry_repo import list_all_spec_identities
from amayama_scraper.transport.port import BrowserCapture
from amayama_scraper.validation.types import ValidationOutcome

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

CHALLENGE_HTML = (FIXTURES / "challenge_cloudflare.html").read_text(encoding="utf-8")
MARKET_INDEX_HTML = (FIXTURES / "market_index" / "valid_multi_entry.html").read_text(
    encoding="utf-8"
)


def _conn():
    conn = connect(":memory:")
    run_migrations(conn)
    save_collection_run(conn, CollectionRun(run_id="run-1"))
    return conn


def _capture(html: str, url: str = "https://x") -> BrowserCapture:
    return BrowserCapture(page_source=html, effective_url=url, captured_at=datetime.now(UTC))


def _noop_sleep(_seconds: float) -> None:
    return None


def test_never_marks_accepted_while_challenge_persists_then_resumes_automatically():
    conn = _conn()
    blob_store, capture_repo = InMemoryRawBlobStore(), InMemoryRawCaptureRepository()
    transport = FakeBrowserTransport()
    # K=2 polls still challenge, 3rd poll returns a valid page.
    transport.queue_current_capture(_capture(CHALLENGE_HTML))
    transport.queue_current_capture(_capture(CHALLENGE_HTML))
    transport.queue_current_capture(_capture(MARKET_INDEX_HTML))

    events: list[tuple[str, dict]] = []
    outcome = await_challenge_resolution(
        transport,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        capture_kind=CaptureKind.MARKET_INDEX,
        source_url_hint="https://x",
        poll_interval=0.0,
        sleep=_noop_sleep,
        on_event=lambda event, **kw: events.append((event, kw)),
    )

    assert outcome.timed_out is False
    assert outcome.result is not None
    assert outcome.result.validation_outcome is ValidationOutcome.ACCEPTED
    assert [e for e, _ in events] == [
        "CHALLENGE_WAITING",
        "CHALLENGE_STILL_PRESENT",
        "CHALLENGE_STILL_PRESENT",
        "CHALLENGE_RESOLVED",
    ]
    # discovery actually happened once the valid page was processed
    assert len(list_all_spec_identities(conn)) > 0


def test_market_index_challenge_pauses_before_any_spec_discovered():
    conn = _conn()
    blob_store, capture_repo = InMemoryRawBlobStore(), InMemoryRawCaptureRepository()
    transport = FakeBrowserTransport()
    transport.queue_current_capture(_capture(CHALLENGE_HTML))
    transport.queue_current_capture(_capture(MARKET_INDEX_HTML))

    outcome = await_challenge_resolution(
        transport,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        capture_kind=CaptureKind.MARKET_INDEX,
        source_url_hint="https://x",
        poll_interval=0.0,
        sleep=_noop_sleep,
    )

    assert outcome.result is not None
    assert outcome.result.validation_outcome is ValidationOutcome.ACCEPTED
    assert len(list_all_spec_identities(conn)) > 0


def test_group_detail_challenge_does_not_affect_already_accepted_groups(tmp_path):
    from amayama_scraper.checkpoint.checkpoint_entry import CheckpointEvent
    from amayama_scraper.checkpoint.upsert import upsert_checkpoint

    conn = _conn()
    # Real SQLite-backed adapters (not the in-memory fakes): GROUP_DETAIL's
    # ACCEPT path writes checkpoint_entry.raw_capture_id, which has a real
    # FK against raw_capture — only the SQLite-backed repo populates that
    # table under this same `conn`.
    blob_store = FilesystemRawBlobStore(tmp_path, conn)
    capture_repo = SqliteRawCaptureRepository(conn)
    # fixture rows so checkpoint_entry.raw_capture_id (FK -> raw_capture) can be satisfied
    conn.execute(
        "INSERT INTO raw_blob (content_hash, size_bytes, storage_path, first_seen_at) "
        "VALUES (?, ?, ?, ?)",
        ("y" * 64, 10, "/blobs/y", "2026-08-26T00:00:00+00:00"),
    )
    conn.execute(
        "INSERT INTO raw_capture (capture_id, run_id, content_hash, source_url, "
        "collected_at, capture_kind, acquisition_mode) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            "cap-x",
            "run-1",
            "y" * 64,
            "https://x/already-done",
            "2026-08-26T00:00:00+00:00",
            "GROUP_DETAIL",
            "AUTOMATED_BROWSER_CDP",
        ),
    )
    # a different group is already ACCEPTED before the challenge occurs
    upsert_checkpoint(
        conn,
        run_id="run-1",
        spec_key="spec-1",
        category_slug="engine",
        group_id="already-done",
        event=CheckpointEvent.START_ATTEMPT,
    )
    upsert_checkpoint(
        conn,
        run_id="run-1",
        spec_key="spec-1",
        category_slug="engine",
        group_id="already-done",
        event=CheckpointEvent.ACCEPT,
        raw_capture_id="cap-x",
    )

    valid_group_html = (FIXTURES / "group_detail" / "valid_group_detail.html").read_text(
        encoding="utf-8"
    )

    transport = FakeBrowserTransport()
    transport.queue_current_capture(_capture(CHALLENGE_HTML))
    transport.queue_current_capture(_capture(valid_group_html))

    await_challenge_resolution(
        transport,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        capture_kind=CaptureKind.GROUP_DETAIL,
        source_url_hint="https://x",
        category_slug="engine",
        group_id="paused-group",
        spec_key="spec-1",
        poll_interval=0.0,
        sleep=_noop_sleep,
    )

    already_done = get_checkpoint_entry(conn, "run-1", "spec-1", "engine", "already-done")
    assert already_done is not None
    assert already_done.status.value == "ACCEPTED"
