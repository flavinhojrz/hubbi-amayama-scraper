"""T093 — combinação --limit-specs + --limit-groups + --spec sobre um
estado com múltiplas specs/grupos descobertos via fake: exatamente os
limites/filtro pedidos são respeitados simultaneamente (User Story 5,
quickstart.md)."""

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
_SPEC_URL_62184 = (
    "https://www.amayama.com/en/genuine-catalogs/epc/volkswagen-overall/amarok/ama-br/s7bc8a-62184"
)

TWO_GROUP_MANIFEST_HTML = """
<html><body>
  <div class="epcVariation__details">
    <div class="epcVariation__filters">
      <div class="epcVariation__schemaGroups">
        <a class="epcVariation__schemaGroup active" data-id="" href="https://x#">All</a>
        <a class="epcVariation__schemaGroup" data-id="4" href="https://x/front-axle-steering">FA</a>
        <a class="epcVariation__schemaGroup" data-id="1" href="https://x/engine">EN</a>
      </div>
    </div>
    <div class="epcVariation__schemas">
      <div class="epcVariation__schema" data-id="407">
        <div class="epcVariation__schema-name"><a href="https://x/front-axle-steering/407">407</a></div>
      </div>
      <div class="epcVariation__schema" data-id="100">
        <div class="epcVariation__schema-name"><a href="https://x/engine/100">100</a></div>
      </div>
    </div>
  </div>
</body></html>
"""

VALID_GROUP_HTML = """
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


def test_limit_specs_and_limit_groups_and_spec_filter_apply_simultaneously(tmp_path):
    conn = _conn()
    save_collection_run(conn, CollectionRun(run_id="run-1"))
    blob_store, capture_repo = (
        FilesystemRawBlobStore(tmp_path, conn),
        SqliteRawCaptureRepository(conn),
    )

    # Discover both specs (62184, 61189) first.
    t0 = FakeBrowserTransport()
    t0.queue_navigate(_capture(MARKET_INDEX_HTML, MARKET_INDEX_URL))
    run_collection_driver(
        t0,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        market_index_url=MARKET_INDEX_URL,
        filters=OperationalFilters(limit_specs=0),
    )
    key_62184 = find_by_model_code_and_catalog_id(conn, "S7BC8A", "62184")[0].stable_key()
    key_61189 = find_by_model_code_and_catalog_id(conn, "S7BC8A", "61189")[0].stable_key()

    # --spec restricts to both explicitly, --limit-specs=1 further truncates
    # to exactly one, --limit-groups=1 truncates that one spec's manifest
    # (2 groups) to exactly 1 processed group.
    t1 = FakeBrowserTransport()
    t1.queue_navigate(_capture(MARKET_INDEX_HTML, MARKET_INDEX_URL))
    t1.queue_navigate(_capture(TWO_GROUP_MANIFEST_HTML, _SPEC_URL_62184))
    # only ONE group capture queued — get_pending_groups() sorts (category_slug,
    # group_id): "engine" < "front-axle-steering", so "engine/100" is the one
    # actually attempted under limit_groups=1.
    t1.queue_navigate(_capture(VALID_GROUP_HTML, "https://x/engine/100"))

    run_collection_driver(
        t1,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        market_index_url=MARKET_INDEX_URL,
        filters=OperationalFilters(
            spec_filter=[key_62184, key_61189], limit_specs=1, limit_groups=1
        ),
    )

    # exactly 1 spec was processed beyond MARKET_INDEX (SPEC_NAVIGATION + 1 group)
    group_level_calls = [
        u for u in t1.navigate_calls if u not in (MARKET_INDEX_URL, _SPEC_URL_62184)
    ]
    assert group_level_calls == ["https://x/engine/100"]
    # the second spec (61189) and the second group (front-axle-steering/407)
    # were never touched — the fake transport was never asked for them.
    assert "https://x/front-axle-steering/407" not in t1.navigate_calls
