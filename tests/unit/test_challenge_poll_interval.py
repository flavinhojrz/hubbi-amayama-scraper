"""T053 — await_challenge_resolution(): intervalo de poll configurável e
respeitado (research.md §11, FR-012). Usa um `sleep` injetado — nunca
time.sleep real em teste."""

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
from amayama_scraper.persistence.db import connect
from amayama_scraper.persistence.migrations.runner import run_migrations
from amayama_scraper.persistence.repositories.checkpoint_repo import save_collection_run
from amayama_scraper.transport.port import BrowserCapture

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
CHALLENGE_HTML = (FIXTURES / "challenge_cloudflare.html").read_text(encoding="utf-8")
MARKET_INDEX_HTML = (FIXTURES / "market_index" / "valid_multi_entry.html").read_text(
    encoding="utf-8"
)


def _capture(html: str) -> BrowserCapture:
    return BrowserCapture(
        page_source=html, effective_url="https://x", captured_at=datetime.now(UTC)
    )


def test_poll_interval_is_respected_between_reads() -> None:
    conn = connect(":memory:")
    run_migrations(conn)
    save_collection_run(conn, CollectionRun(run_id="run-1"))
    blob_store, capture_repo = InMemoryRawBlobStore(), InMemoryRawCaptureRepository()

    transport = FakeBrowserTransport()
    transport.queue_current_capture(_capture(CHALLENGE_HTML))
    transport.queue_current_capture(_capture(CHALLENGE_HTML))
    transport.queue_current_capture(_capture(MARKET_INDEX_HTML))

    sleeps: list[float] = []
    await_challenge_resolution(
        transport,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        capture_kind=CaptureKind.MARKET_INDEX,
        source_url_hint="https://x",
        poll_interval=3.5,
        sleep=sleeps.append,
    )

    assert sleeps == [3.5, 3.5, 3.5]  # one sleep before each of the 3 reads
