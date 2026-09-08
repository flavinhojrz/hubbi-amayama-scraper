"""T118 — challenge em uma spec não corrompe/revisita o progresso de outra
spec já VALID (US3 cenário 3, FR-028 sequencial)."""

from __future__ import annotations

from datetime import UTC, datetime
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
_URL_62184 = (
    "https://www.amayama.com/en/genuine-catalogs/epc/volkswagen-overall/amarok/ama-br/s7bc8a-62184"
)
_URL_61189 = (
    "https://www.amayama.com/en/genuine-catalogs/epc/volkswagen-overall/amarok/ama-br/s7bc8a-61189"
)
CHALLENGE_HTML = (FIXTURES / "challenge_cloudflare.html").read_text(encoding="utf-8")

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


def _group_html(oem: str) -> str:
    return f"""
<html><body><div class="epcVariation__details"><div class="epcSchema__schemas">
  <div class="epcSchema__schema" data-id="SCH-1"><table class="entriesTable">
    <tr data-key="A01"><td class="entriesTable__number">{oem}</td>
    <td class="entriesTable__description">Control arm</td>
    <td class="entriesTable__period">08.2010-12.2015</td>
    <td class="entriesTable__required">1</td></tr>
  </table></div>
</div></div></body></html>
"""


def _capture(html: str, url: str) -> BrowserCapture:
    return BrowserCapture(page_source=html, effective_url=url, captured_at=datetime.now(UTC))


def test_challenge_on_second_spec_does_not_disturb_first_specs_valid_snapshot(tmp_path):
    conn = connect(":memory:")
    run_migrations(conn)
    save_collection_run(conn, CollectionRun(run_id="run-1"))
    blob_store = FilesystemRawBlobStore(tmp_path, conn)
    capture_repo = SqliteRawCaptureRepository(conn)

    # Phase 0: discovery only.
    t0 = FakeBrowserTransport()
    t0.queue_navigate(_capture(MARKET_INDEX_HTML, MARKET_INDEX_URL))
    run_collection_driver(
        t0,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        context=AMAROK_CONTEXT,
        filters=OperationalFilters(limit_specs=0),
    )
    key_62184 = find_by_model_code_and_catalog_id(conn, "S7BC8A", "62184")[0].stable_key()
    key_61189 = find_by_model_code_and_catalog_id(conn, "S7BC8A", "61189")[0].stable_key()

    # Phase 1: fully complete spec 62184 -> VALID.
    t1b = FakeBrowserTransport()
    t1b.queue_navigate(_capture(MARKET_INDEX_HTML, MARKET_INDEX_URL))
    t1b.queue_navigate(_capture(MANIFEST_HTML, _URL_62184))
    t1b.queue_navigate(_capture(_group_html("1K0407151"), "https://x/front-axle-steering/407"))
    run_collection_driver(
        t1b,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        context=AMAROK_CONTEXT,
        filters=OperationalFilters(spec_filter=[key_62184]),
    )
    current_62184_before = get_current_state(conn, key_62184)
    assert current_62184_before is not None
    snapshot_62184_before = get_snapshot(conn, current_62184_before.latest_snapshot_id)
    assert snapshot_62184_before.state == SnapshotState.VALID

    # Phase 2: process spec 61189 — hits a challenge on its group, resolves,
    # in the SAME driver invocation (blocking poll loop).
    t2 = FakeBrowserTransport()
    t2.queue_navigate(_capture(MARKET_INDEX_HTML, MARKET_INDEX_URL))
    t2.queue_navigate(_capture(MANIFEST_HTML, _URL_61189))
    t2.queue_current_capture(_capture(CHALLENGE_HTML, "https://x/front-axle-steering/407"))
    t2.queue_current_capture(
        _capture(_group_html("1K0407152"), "https://x/front-axle-steering/407")
    )
    # the FIRST navigate() call for the group also needs a queued response
    # (it triggers the challenge outcome), poll loop then uses current_capture().
    t2.queue_navigate(_capture(CHALLENGE_HTML, "https://x/front-axle-steering/407"))

    run_collection_driver(
        t2,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        context=AMAROK_CONTEXT,
        filters=OperationalFilters(spec_filter=[key_61189]),
        poll_interval=0.0,
        sleep=lambda _s: None,
    )

    current_61189 = get_current_state(conn, key_61189)
    assert current_61189 is not None
    assert get_snapshot(conn, current_61189.latest_snapshot_id).state == SnapshotState.VALID

    # spec 62184 was never touched during phase 2 — same snapshot as before.
    current_62184_after = get_current_state(conn, key_62184)
    assert current_62184_after.latest_snapshot_id == current_62184_before.latest_snapshot_id
