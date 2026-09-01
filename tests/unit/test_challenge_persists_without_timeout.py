"""T061 — challenge persistindo indefinidamente sob --challenge-timeout não
configurado (research.md §11). Distinto de test_challenge_timeout.py: aqui
verificamos que, a cada poll ainda-challenge, a unidade nunca é classificada
como algo diferente de "ainda aguardando" — nunca REQUIRES_EXPLICIT_RETRY,
nunca ACCEPTED — mesmo depois de muitas iterações."""

from __future__ import annotations

import contextlib
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


class _StopAfterN(Exception):
    pass


def test_many_challenge_polls_never_self_resolve_or_time_out() -> None:
    conn = connect(":memory:")
    run_migrations(conn)
    save_collection_run(conn, CollectionRun(run_id="run-1"))
    blob_store, capture_repo = InMemoryRawBlobStore(), InMemoryRawCaptureRepository()

    n_polls = 30
    transport = FakeBrowserTransport()
    for _ in range(n_polls):
        transport.queue_current_capture(
            BrowserCapture(
                page_source=CHALLENGE_HTML, effective_url="https://x", captured_at=datetime.now(UTC)
            )
        )

    events: list[str] = []
    count = {"n": 0}

    def _sleep(_seconds: float) -> None:
        count["n"] += 1
        if count["n"] >= n_polls:
            raise _StopAfterN

    with contextlib.suppress(_StopAfterN):
        await_challenge_resolution(
            transport,
            conn,
            blob_store,
            capture_repo,
            run_id="run-1",
            capture_kind=CaptureKind.MARKET_INDEX,
            source_url_hint="https://x",
            poll_interval=0.0,
            sleep=_sleep,
            timeout=None,
            on_event=lambda event, **kw: events.append(event),
        )

    # every completed poll before the forced stop reported "still present",
    # never a resolution and never a timeout — no self-abandonment.
    assert "CHALLENGE_RESOLVED" not in events
    assert "CHALLENGE_TIMEOUT" not in events
    assert events.count("CHALLENGE_STILL_PRESENT") >= n_polls - 1
