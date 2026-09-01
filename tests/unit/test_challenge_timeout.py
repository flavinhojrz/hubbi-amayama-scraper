"""T054 — await_challenge_resolution(): --challenge-timeout opcional
(research.md §11). Sem timeout, espera indefinidamente (nunca desiste
sozinha); com timeout excedido, desiste apenas da unidade corrente."""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime, timedelta
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


def _capture(html: str) -> BrowserCapture:
    return BrowserCapture(
        page_source=html, effective_url="https://x", captured_at=datetime.now(UTC)
    )


def _conn():
    conn = connect(":memory:")
    run_migrations(conn)
    save_collection_run(conn, CollectionRun(run_id="run-1"))
    return conn


def test_gives_up_only_this_unit_when_timeout_exceeded() -> None:
    conn = _conn()
    blob_store, capture_repo = InMemoryRawBlobStore(), InMemoryRawCaptureRepository()
    transport = FakeBrowserTransport()
    for _ in range(10):
        transport.queue_current_capture(_capture(CHALLENGE_HTML))

    base = datetime(2026, 8, 28, 12, 0, 0, tzinfo=UTC)
    ticks = iter([base + timedelta(seconds=i * 5) for i in range(10)])

    outcome = await_challenge_resolution(
        transport,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        capture_kind=CaptureKind.MARKET_INDEX,
        source_url_hint="https://x",
        poll_interval=0.0,
        sleep=lambda _s: None,
        timeout=12.0,
        now=lambda: next(ticks),
    )

    assert outcome.timed_out is True
    assert outcome.result is None


class _StoppedAfterManyPolls(Exception):
    """Sentinel used only to break the (deliberately unbounded) wait loop
    deterministically once the test has observed "enough" iterations."""


def test_waits_indefinitely_without_timeout_configured() -> None:
    conn = _conn()
    blob_store, capture_repo = InMemoryRawBlobStore(), InMemoryRawCaptureRepository()
    transport = FakeBrowserTransport()
    n_polls = 50
    for _ in range(n_polls):
        transport.queue_current_capture(_capture(CHALLENGE_HTML))

    calls = {"count": 0}

    def _bounded_sleep(_seconds: float) -> None:
        calls["count"] += 1
        if calls["count"] >= n_polls:
            raise _StoppedAfterManyPolls

    with contextlib.suppress(_StoppedAfterManyPolls):
        await_challenge_resolution(
            transport,
            conn,
            blob_store,
            capture_repo,
            run_id="run-1",
            capture_kind=CaptureKind.MARKET_INDEX,
            source_url_hint="https://x",
            poll_interval=0.0,
            sleep=_bounded_sleep,
            timeout=None,
        )

    assert calls["count"] >= n_polls  # never gave up on its own before this
