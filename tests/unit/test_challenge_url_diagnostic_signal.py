"""T062/T063 — effective_url divergente é sinal diagnóstico não-autoritativo,
nunca decide ACCEPTED/REJECTED por si só (FR-015, contracts/browser-transport-
contract.md §4)."""

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
from amayama_scraper.validation.types import ValidationOutcome

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
CHALLENGE_HTML = (FIXTURES / "challenge_cloudflare.html").read_text(encoding="utf-8")
MARKET_INDEX_HTML = (FIXTURES / "market_index" / "valid_multi_entry.html").read_text(
    encoding="utf-8"
)


def test_diverging_effective_url_is_reported_but_does_not_block_acceptance() -> None:
    conn = connect(":memory:")
    run_migrations(conn)
    save_collection_run(conn, CollectionRun(run_id="run-1"))
    blob_store, capture_repo = InMemoryRawBlobStore(), InMemoryRawCaptureRepository()

    transport = FakeBrowserTransport()
    transport.queue_current_capture(
        BrowserCapture(
            page_source=CHALLENGE_HTML,
            effective_url="https://x/expected",
            captured_at=datetime.now(UTC),
        )
    )
    # effective_url differs from the originally expected one, but the
    # structure IS the valid, expected one for this capture_kind.
    transport.queue_current_capture(
        BrowserCapture(
            page_source=MARKET_INDEX_HTML,
            effective_url="https://x/redirected-elsewhere",
            captured_at=datetime.now(UTC),
        )
    )

    events: list[tuple[str, dict]] = []
    outcome = await_challenge_resolution(
        transport,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        capture_kind=CaptureKind.MARKET_INDEX,
        source_url_hint="https://x/expected",
        poll_interval=0.0,
        sleep=lambda _s: None,
        on_event=lambda event, **kw: events.append((event, kw)),
    )

    # the diagnostic signal was reported for the still-challenge poll...
    still_present = [kw for e, kw in events if e == "CHALLENGE_STILL_PRESENT"]
    assert still_present[0]["observed_url"] == "https://x/expected"
    # ...but the divergent URL on the RESOLVING poll never blocked acceptance:
    # structure alone (classify_capture()) decided the outcome.
    assert outcome.result is not None
    assert outcome.result.validation_outcome is ValidationOutcome.ACCEPTED
