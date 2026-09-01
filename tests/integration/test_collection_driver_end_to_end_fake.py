"""T080-T085 — laço completo MARKET_INDEX -> SPEC_NAVIGATION -> GROUP_DETAIL
-> try_finalize_spec_entry(), tudo via FakeBrowserTransport (US2, SC-002).

Reaproveita as fixtures MANIFEST_HTML/GROUP_HTML já comprovadas de
tests/integration/test_pipeline_end_to_end.py (T250, 001) — nenhuma
fixture nova de domínio é necessária."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

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
from amayama_scraper.persistence.repositories.current_state_repo import get_current_state
from amayama_scraper.persistence.repositories.snapshot_repo import get_snapshot
from amayama_scraper.persistence.repositories.spec_registry_repo import (
    find_by_model_code_and_catalog_id,
)
from amayama_scraper.snapshots.snapshot import SnapshotState
from amayama_scraper.transport.port import BrowserCapture

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
MARKET_INDEX_HTML = (FIXTURES / "market_index" / "same_model_code_diff_catalog.html").read_text(
    encoding="utf-8"
)
MARKET_INDEX_URL = (
    "https://www.amayama.com/en/genuine-catalogs/epc/volkswagen-overall/amarok/ama-br"
)

# Same proven-valid fixtures as tests/integration/test_pipeline_end_to_end.py (T250, 001).
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
    return conn


_SPEC_URL = (
    "https://www.amayama.com/en/genuine-catalogs/epc/volkswagen-overall/amarok/ama-br/s7bc8a-62184"
)


def _discover_and_get_key(conn, blob_store, capture_repo, run_id: str) -> str:
    """Discovery-only pass (limit_specs=0), then look up the deterministic
    stable_key for S7BC8A/62184 — avoids depending on list ordering when
    selecting which of the two discovered specs to drive through in full."""
    transport = FakeBrowserTransport()
    transport.queue_navigate(_capture(MARKET_INDEX_HTML, MARKET_INDEX_URL))
    run_collection_driver(
        transport,
        conn,
        blob_store,
        capture_repo,
        run_id=run_id,
        market_index_url=MARKET_INDEX_URL,
        filters=OperationalFilters(limit_specs=0),
    )
    return find_by_model_code_and_catalog_id(conn, "S7BC8A", "62184")[0].stable_key()


def test_full_pipeline_reaches_valid_snapshot_via_fake_transport_only(tmp_path):
    conn = _conn()
    save_collection_run(conn, CollectionRun(run_id="run-1"))
    blob_store, capture_repo = (
        FilesystemRawBlobStore(tmp_path, conn),
        SqliteRawCaptureRepository(conn),
    )
    key = _discover_and_get_key(conn, blob_store, capture_repo, "run-1")

    transport = FakeBrowserTransport()
    transport.queue_navigate(_capture(MARKET_INDEX_HTML, MARKET_INDEX_URL))
    transport.queue_navigate(_capture(MANIFEST_HTML, _SPEC_URL))
    transport.queue_navigate(_capture(GROUP_HTML, "https://x/front-axle-steering/407"))

    run_collection_driver(
        transport,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        market_index_url=MARKET_INDEX_URL,
        filters=OperationalFilters(spec_filter=[key]),
    )

    current = get_current_state(conn, key)
    assert current is not None
    snapshot = get_snapshot(conn, current.latest_snapshot_id)
    assert snapshot is not None
    assert snapshot.state == SnapshotState.VALID
    assert snapshot.collection_complete is True


def test_second_run_skips_already_valid_spec_without_any_further_navigation(tmp_path):
    conn = _conn()
    save_collection_run(conn, CollectionRun(run_id="run-1"))
    blob_store, capture_repo = (
        FilesystemRawBlobStore(tmp_path, conn),
        SqliteRawCaptureRepository(conn),
    )
    key = _discover_and_get_key(conn, blob_store, capture_repo, "run-1")

    transport = FakeBrowserTransport()
    transport.queue_navigate(_capture(MARKET_INDEX_HTML, MARKET_INDEX_URL))
    transport.queue_navigate(_capture(MANIFEST_HTML, _SPEC_URL))
    transport.queue_navigate(_capture(GROUP_HTML, "https://x/front-axle-steering/407"))

    run_collection_driver(
        transport,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        market_index_url=MARKET_INDEX_URL,
        filters=OperationalFilters(spec_filter=[key]),
    )
    assert get_current_state(conn, key) is not None  # sanity: VALID from first run

    # Second run: only the MARKET_INDEX capture is queued — if the driver
    # tried to renavigate the already-VALID spec, it would starve the fake
    # and raise AssertionError.
    save_collection_run(conn, CollectionRun(run_id="run-2"))
    transport_2 = FakeBrowserTransport()
    transport_2.queue_navigate(_capture(MARKET_INDEX_HTML, MARKET_INDEX_URL))

    run_collection_driver(
        transport_2,
        conn,
        blob_store,
        capture_repo,
        run_id="run-2",
        market_index_url=MARKET_INDEX_URL,
        filters=OperationalFilters(spec_filter=[key]),
    )

    assert transport_2.navigate_calls == [
        MARKET_INDEX_URL
    ]  # never navigated to the VALID spec again


def test_force_recollects_an_already_valid_spec(tmp_path):
    conn = _conn()
    save_collection_run(conn, CollectionRun(run_id="run-1"))
    blob_store, capture_repo = (
        FilesystemRawBlobStore(tmp_path, conn),
        SqliteRawCaptureRepository(conn),
    )
    key = _discover_and_get_key(conn, blob_store, capture_repo, "run-1")

    transport = FakeBrowserTransport()
    transport.queue_navigate(_capture(MARKET_INDEX_HTML, MARKET_INDEX_URL))
    transport.queue_navigate(_capture(MANIFEST_HTML, _SPEC_URL))
    transport.queue_navigate(_capture(GROUP_HTML, "https://x/front-axle-steering/407"))
    run_collection_driver(
        transport,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        market_index_url=MARKET_INDEX_URL,
        filters=OperationalFilters(spec_filter=[key]),
    )
    first_snapshot_id = get_current_state(conn, key).latest_snapshot_id

    save_collection_run(conn, CollectionRun(run_id="run-2"))
    transport_2 = FakeBrowserTransport()
    transport_2.queue_navigate(_capture(MARKET_INDEX_HTML, MARKET_INDEX_URL))
    transport_2.queue_navigate(_capture(MANIFEST_HTML, _SPEC_URL))
    transport_2.queue_navigate(_capture(GROUP_HTML, "https://x/front-axle-steering/407"))

    run_collection_driver(
        transport_2,
        conn,
        blob_store,
        capture_repo,
        run_id="run-2",
        market_index_url=MARKET_INDEX_URL,
        filters=OperationalFilters(spec_filter=[key], force=[key]),
    )

    second_snapshot_id = get_current_state(conn, key).latest_snapshot_id
    assert second_snapshot_id != first_snapshot_id  # a genuinely new snapshot was created
    # the prior snapshot/raw is preserved, not destroyed (FR-032a, DEC-008)
    assert get_snapshot(conn, first_snapshot_id) is not None
