"""Blocker 3 (Codex) — --min-interval propagado até run_collection_driver()
e efetivamente respeitado entre navegações reais sucessivas (FR-029, User
Story 6). Nunca aplicado à primeira navegação; nunca confundido com
poll_interval (challenge) nem com o retry/backoff de transporte (que vive
dentro do adapter concreto, invisível aqui); min_interval=0 nunca introduz
espera. Testes usam sleep/now injetados — nenhum time.sleep real."""

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
from amayama_scraper.persistence.db import connect
from amayama_scraper.persistence.migrations.runner import run_migrations
from amayama_scraper.persistence.repositories.checkpoint_repo import save_collection_run
from amayama_scraper.transport.port import BrowserCapture

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
MARKET_INDEX_HTML = (FIXTURES / "market_index" / "same_model_code_diff_catalog.html").read_text(
    encoding="utf-8"
)
MARKET_INDEX_URL = (
    "https://www.amayama.com/en/genuine-catalogs/epc/volkswagen-overall/amarok/ama-br"
)
_URL_62184 = (
    "https://www.amayama.com/en/genuine-catalogs/epc/volkswagen-overall/amarok/ama-br/s7bc8a-62184"
)

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

GROUP_HTML = """
<html><body><div class="epcVariation__details"><div class="epcSchema__schemas">
  <div class="epcSchema__schema" data-id="SCH-1"><table class="entriesTable">
    <tr data-key="A01"><td class="entriesTable__number">1K0407151</td>
    <td class="entriesTable__description">Control arm</td>
    <td class="entriesTable__period">08.2010-12.2015</td>
    <td class="entriesTable__required">1</td></tr>
  </table></div>
</div></div></body></html>
"""


def _capture(html: str, url: str) -> BrowserCapture:
    return BrowserCapture(page_source=html, effective_url=url, captured_at=datetime.now(UTC))


def _conn():
    conn = connect(":memory:")
    run_migrations(conn)
    save_collection_run(conn, CollectionRun(run_id="run-1"))
    return conn


def _clock(start: datetime, step_seconds: float = 0.0):
    """A fake `now()` that advances by `step_seconds` on every call (models
    time elapsed by "real work", e.g. parsing/network), independent of the
    `sleep()` fake, which only advances when the throttle asks it to."""
    state = {"t": start}

    def _now() -> datetime:
        state["t"] += timedelta(seconds=step_seconds)
        return state["t"]

    def _advance(seconds: float) -> None:
        state["t"] += timedelta(seconds=seconds)

    return _now, _advance


def test_second_navigation_sleeps_for_the_remaining_min_interval(tmp_path):
    from amayama_scraper.persistence.adapters.filesystem_raw_blob_store import (
        FilesystemRawBlobStore,
    )
    from amayama_scraper.persistence.adapters.sqlite_raw_capture_repository import (
        SqliteRawCaptureRepository,
    )

    conn = _conn()
    blob_store = FilesystemRawBlobStore(tmp_path, conn)
    capture_repo = SqliteRawCaptureRepository(conn)

    transport = FakeBrowserTransport()
    transport.queue_navigate(_capture(MARKET_INDEX_HTML, MARKET_INDEX_URL))
    transport.queue_navigate(_capture(MANIFEST_HTML, _URL_62184))
    transport.queue_navigate(_capture(GROUP_HTML, "https://x/front-axle-steering/407"))

    now, advance = _clock(datetime(2026, 8, 29, tzinfo=UTC))
    sleeps: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        advance(seconds)  # simulate time actually passing while asleep

    run_collection_driver(
        transport,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        context=AMAROK_CONTEXT,
        filters=OperationalFilters(spec_filter=None, limit_specs=1),
        min_interval=10.0,
        sleep=fake_sleep,
        now=now,
    )

    # 3 navigations total (MARKET_INDEX, SPEC_NAVIGATION, GROUP_DETAIL) ->
    # exactly 2 throttle sleeps (never before the first navigation).
    assert len(sleeps) == 2
    assert all(s == 10.0 for s in sleeps)


def test_first_navigation_never_waits(tmp_path):
    from amayama_scraper.persistence.adapters.filesystem_raw_blob_store import (
        FilesystemRawBlobStore,
    )
    from amayama_scraper.persistence.adapters.sqlite_raw_capture_repository import (
        SqliteRawCaptureRepository,
    )

    conn = _conn()
    blob_store = FilesystemRawBlobStore(tmp_path, conn)
    capture_repo = SqliteRawCaptureRepository(conn)

    transport = FakeBrowserTransport()
    transport.queue_navigate(_capture(MARKET_INDEX_HTML, MARKET_INDEX_URL))

    now, _advance = _clock(datetime(2026, 8, 29, tzinfo=UTC))
    sleeps: list[float] = []
    run_collection_driver(
        transport,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        context=AMAROK_CONTEXT,
        filters=OperationalFilters(limit_specs=0),
        min_interval=30.0,
        sleep=sleeps.append,
        now=now,
    )
    assert sleeps == []  # only one navigation ever happened — no throttle triggered


def test_zero_min_interval_never_sleeps(tmp_path):
    from amayama_scraper.persistence.adapters.filesystem_raw_blob_store import (
        FilesystemRawBlobStore,
    )
    from amayama_scraper.persistence.adapters.sqlite_raw_capture_repository import (
        SqliteRawCaptureRepository,
    )

    conn = _conn()
    blob_store = FilesystemRawBlobStore(tmp_path, conn)
    capture_repo = SqliteRawCaptureRepository(conn)

    transport = FakeBrowserTransport()
    transport.queue_navigate(_capture(MARKET_INDEX_HTML, MARKET_INDEX_URL))
    transport.queue_navigate(_capture(MANIFEST_HTML, _URL_62184))
    transport.queue_navigate(_capture(GROUP_HTML, "https://x/front-axle-steering/407"))

    now, _advance = _clock(datetime(2026, 8, 29, tzinfo=UTC))
    sleeps: list[float] = []
    run_collection_driver(
        transport,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        context=AMAROK_CONTEXT,
        filters=OperationalFilters(limit_specs=1),
        min_interval=0.0,  # default
        sleep=sleeps.append,
        now=now,
    )
    assert sleeps == []


def test_already_elapsed_time_reduces_or_removes_the_wait(tmp_path):
    """If enough wall-clock time already passed between navigations (e.g.
    slow parsing), the throttle should not add a redundant full wait."""
    from amayama_scraper.persistence.adapters.filesystem_raw_blob_store import (
        FilesystemRawBlobStore,
    )
    from amayama_scraper.persistence.adapters.sqlite_raw_capture_repository import (
        SqliteRawCaptureRepository,
    )

    conn = _conn()
    blob_store = FilesystemRawBlobStore(tmp_path, conn)
    capture_repo = SqliteRawCaptureRepository(conn)

    transport = FakeBrowserTransport()
    transport.queue_navigate(_capture(MARKET_INDEX_HTML, MARKET_INDEX_URL))
    transport.queue_navigate(_capture(MANIFEST_HTML, _URL_62184))

    # 15s of "real work" elapse between navigations on every now() call.
    now, _advance = _clock(datetime(2026, 8, 29, tzinfo=UTC), step_seconds=15.0)
    sleeps: list[float] = []
    run_collection_driver(
        transport,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        context=AMAROK_CONTEXT,
        filters=OperationalFilters(limit_specs=1, limit_groups=0),
        min_interval=10.0,  # less than the 15s already elapsed
        sleep=sleeps.append,
        now=now,
    )
    assert sleeps == []  # enough time already passed — no additional wait needed


def test_min_interval_is_independent_of_transport_retry_backoff(tmp_path):
    """A FakeBrowserTransport never retries internally (retry/backoff lives
    exclusively inside ChromeCdpTransport, research.md §10) — this test
    documents that min_interval throttling in the driver is a completely
    separate mechanism from transport-level retry backoff, never mixed."""
    from amayama_scraper.persistence.adapters.filesystem_raw_blob_store import (
        FilesystemRawBlobStore,
    )
    from amayama_scraper.persistence.adapters.sqlite_raw_capture_repository import (
        SqliteRawCaptureRepository,
    )

    conn = _conn()
    blob_store = FilesystemRawBlobStore(tmp_path, conn)
    capture_repo = SqliteRawCaptureRepository(conn)

    transport = FakeBrowserTransport()
    transport.queue_navigate(_capture(MARKET_INDEX_HTML, MARKET_INDEX_URL))
    transport.queue_navigate(_capture(MANIFEST_HTML, _URL_62184))

    now, advance = _clock(datetime(2026, 8, 29, tzinfo=UTC))
    sleep_calls: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)
        advance(seconds)

    run_collection_driver(
        transport,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        context=AMAROK_CONTEXT,
        filters=OperationalFilters(limit_specs=1, limit_groups=0),
        min_interval=5.0,
        poll_interval=999.0,  # would be obviously wrong if min_interval reused poll_interval
        sleep=fake_sleep,
        now=now,
    )
    # exactly one throttle sleep (2nd navigation), using min_interval (5.0),
    # never poll_interval (999.0) — they are never conflated.
    assert sleep_calls == [5.0]
