"""Cobertura dos ramos de challenge-timeout e rejeição sem challenge do
driver em cada um dos três níveis (MARKET_INDEX/SPEC_NAVIGATION/GROUP_DETAIL)
— contracts/browser-transport-contract.md §3."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from tests.support import AMAROK_CONTEXT
from tests.unit.fakes import FakeBrowserTransport

from amayama_scraper.checkpoint.collection_run import CollectionRun
from amayama_scraper.orchestration.collection_driver import (
    OperationalFilters,
    run_collection_driver,
)
from amayama_scraper.persistence.adapters.filesystem_raw_blob_store import FilesystemRawBlobStore
from amayama_scraper.persistence.adapters.sqlite_raw_capture_repository import (
    SqliteRawCaptureRepository,
)
from amayama_scraper.persistence.db import connect
from amayama_scraper.persistence.migrations.runner import run_migrations
from amayama_scraper.persistence.repositories.checkpoint_repo import save_collection_run
from amayama_scraper.persistence.repositories.manifest_repo import get_authoritative
from amayama_scraper.persistence.repositories.spec_registry_repo import (
    find_by_model_code_and_catalog_id,
)
from amayama_scraper.transport.port import BrowserCapture

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
MARKET_INDEX_HTML = (FIXTURES / "market_index" / "same_model_code_diff_catalog.html").read_text(
    encoding="utf-8"
)
MARKET_INDEX_URL = (
    "https://www.amayama.com/en/genuine-catalogs/epc/volkswagen-overall/amarok/ama-br"
)
_SPEC_URL = (
    "https://www.amayama.com/en/genuine-catalogs/epc/volkswagen-overall/amarok/ama-br/s7bc8a-62184"
)
CHALLENGE_HTML = (FIXTURES / "challenge_cloudflare.html").read_text(encoding="utf-8")
INVALID_HTML = "<html><body><h1>not epc content</h1></body></html>"

MANIFEST_HTML = """
<html><body>
  <div class="epcVariation__details">
    <div class="epcVariation__filters">
      <div class="epcVariation__schemaGroups">
        <a class="epcVariation__schemaGroup active" data-id="" href="https://x#">All</a>
        <a class="epcVariation__schemaGroup" data-id="4" href="https://x/front-axle-steering">FA</a>
      </div>
    </div>
    <div class="epcVariation__schemas">
      <div class="epcVariation__schema" data-id="407">
        <div class="epcVariation__schema-name"><a href="https://x/front-axle-steering/407">407</a></div>
      </div>
    </div>
  </div>
</body></html>
"""


def _capture(html: str, url: str = "https://x") -> BrowserCapture:
    return BrowserCapture(page_source=html, effective_url=url, captured_at=datetime.now(UTC))


def _conn():
    conn = connect(":memory:")
    run_migrations(conn)
    save_collection_run(conn, CollectionRun(run_id="run-1"))
    return conn


def _bounded_now(base: datetime, step_seconds: float = 5.0):
    ticks = iter(base + timedelta(seconds=i * step_seconds) for i in range(200))
    return lambda: next(ticks)


def test_market_index_challenge_timeout_aborts_run_without_discovering_anything(tmp_path):
    conn = _conn()
    blob_store = FilesystemRawBlobStore(tmp_path, conn)
    capture_repo = SqliteRawCaptureRepository(conn)
    transport = FakeBrowserTransport()
    transport.queue_navigate(_capture(CHALLENGE_HTML, MARKET_INDEX_URL))
    for _ in range(50):
        transport.queue_current_capture(_capture(CHALLENGE_HTML, MARKET_INDEX_URL))

    events: list[str] = []
    run_collection_driver(
        transport,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        context=AMAROK_CONTEXT,
        filters=OperationalFilters(),
        poll_interval=0.0,
        sleep=lambda _s: None,
        challenge_timeout=10.0,
        now=_bounded_now(datetime(2026, 8, 28, tzinfo=UTC)),
        on_event=lambda event, **kw: events.append(event),
    )

    assert "RUN_ABORTED" in events
    assert "RUN_STARTED" not in events  # discovery never proceeded


def test_spec_navigation_challenge_timeout_skips_only_that_spec(tmp_path):
    conn = _conn()
    blob_store = FilesystemRawBlobStore(tmp_path, conn)
    capture_repo = SqliteRawCaptureRepository(conn)

    transport = FakeBrowserTransport()
    transport.queue_navigate(_capture(MARKET_INDEX_HTML, MARKET_INDEX_URL))
    transport.queue_navigate(_capture(CHALLENGE_HTML, _SPEC_URL))
    for _ in range(50):
        transport.queue_current_capture(_capture(CHALLENGE_HTML, _SPEC_URL))

    events: list[str] = []
    run_collection_driver(
        transport,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        context=AMAROK_CONTEXT,
        filters=OperationalFilters(limit_specs=1),
        poll_interval=0.0,
        sleep=lambda _s: None,
        challenge_timeout=10.0,
        now=_bounded_now(datetime(2026, 8, 28, tzinfo=UTC)),
        on_event=lambda event, **kw: events.append(event),
    )

    assert "SPEC_NAVIGATION_CHALLENGE_TIMEOUT" in events
    assert "RUN_SUMMARY" in events  # the run itself completes normally, only that spec is skipped


def test_spec_navigation_rejected_without_challenge_is_reported_and_skipped(tmp_path):
    conn = _conn()
    blob_store = FilesystemRawBlobStore(tmp_path, conn)
    capture_repo = SqliteRawCaptureRepository(conn)

    transport = FakeBrowserTransport()
    transport.queue_navigate(_capture(MARKET_INDEX_HTML, MARKET_INDEX_URL))
    transport.queue_navigate(_capture(INVALID_HTML, _SPEC_URL))  # INVALID, not CHALLENGE

    events: list[str] = []
    run_collection_driver(
        transport,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        context=AMAROK_CONTEXT,
        filters=OperationalFilters(limit_specs=1),
        on_event=lambda event, **kw: events.append(event),
    )

    assert "SPEC_NAVIGATION_REJECTED" in events
    assert "GROUP_ACCEPTED" not in events


def test_group_detail_challenge_timeout_skips_only_that_group(tmp_path):
    conn = _conn()
    blob_store = FilesystemRawBlobStore(tmp_path, conn)
    capture_repo = SqliteRawCaptureRepository(conn)

    transport = FakeBrowserTransport()
    transport.queue_navigate(_capture(MARKET_INDEX_HTML, MARKET_INDEX_URL))
    transport.queue_navigate(_capture(MANIFEST_HTML, _SPEC_URL))
    transport.queue_navigate(_capture(CHALLENGE_HTML, "https://x/front-axle-steering/407"))
    for _ in range(50):
        transport.queue_current_capture(
            _capture(CHALLENGE_HTML, "https://x/front-axle-steering/407")
        )

    events: list[str] = []
    run_collection_driver(
        transport,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        context=AMAROK_CONTEXT,
        filters=OperationalFilters(limit_specs=1),
        poll_interval=0.0,
        sleep=lambda _s: None,
        challenge_timeout=10.0,
        now=_bounded_now(datetime(2026, 8, 28, tzinfo=UTC)),
        on_event=lambda event, **kw: events.append(event),
    )

    assert "GROUP_CHALLENGE_TIMEOUT" in events
    # the manifest was still persisted even though the group itself timed out
    key = find_by_model_code_and_catalog_id(conn, "S7BC8A", "62184")[0].stable_key()
    assert get_authoritative(conn, key, "run-1") is not None
