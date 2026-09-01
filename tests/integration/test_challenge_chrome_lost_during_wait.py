"""T059 — Chrome fechado durante a espera de challenge (research.md §11).

current_capture() levanta ChromeNotReachableError — a exceção é propagada
(não engolida), interrompendo a execução com a unidade preservada em
estado retomável (nenhuma escrita adicional ocorre)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
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
from amayama_scraper.persistence.repositories.spec_registry_repo import list_all_spec_identities
from amayama_scraper.transport.errors import ChromeNotReachableError
from amayama_scraper.transport.port import BrowserCapture

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
CHALLENGE_HTML = (FIXTURES / "challenge_cloudflare.html").read_text(encoding="utf-8")


def _capture(html: str) -> BrowserCapture:
    return BrowserCapture(
        page_source=html, effective_url="https://x", captured_at=datetime.now(UTC)
    )


def test_chrome_lost_during_challenge_wait_propagates_and_writes_nothing_new():
    conn = connect(":memory:")
    run_migrations(conn)
    save_collection_run(conn, CollectionRun(run_id="run-1"))
    blob_store, capture_repo = InMemoryRawBlobStore(), InMemoryRawCaptureRepository()

    transport = FakeBrowserTransport()
    transport.queue_current_capture(_capture(CHALLENGE_HTML))
    transport.queue_current_capture(ChromeNotReachableError("Chrome window closed"))

    events: list[str] = []
    with pytest.raises(ChromeNotReachableError):
        await_challenge_resolution(
            transport,
            conn,
            blob_store,
            capture_repo,
            run_id="run-1",
            capture_kind=CaptureKind.MARKET_INDEX,
            source_url_hint="https://x",
            poll_interval=0.0,
            sleep=lambda _s: None,
            on_event=lambda event, **kw: events.append(event),
        )

    # nothing was discovered as a result of the lost session
    assert list_all_spec_identities(conn) == []
    assert events == ["CHALLENGE_WAITING", "CHALLENGE_STILL_PRESENT"]
