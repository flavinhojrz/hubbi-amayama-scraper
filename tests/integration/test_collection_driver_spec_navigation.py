"""T080/T081 — laço de nível B (SPEC_NAVIGATION): só executa quando
get_authoritative() ainda é None para (spec_key, run_id); manifesto real
persistido; uma segunda passada não recaptura SPEC_NAVIGATION quando o
manifesto já existe (FR-007, US2 cenário 1)."""

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


def _capture(html: str, url: str) -> BrowserCapture:
    return BrowserCapture(page_source=html, effective_url=url, captured_at=datetime.now(UTC))


def _conn():
    conn = connect(":memory:")
    run_migrations(conn)
    return conn


def test_spec_navigation_manifest_persisted_and_not_recaptured_on_second_pass(tmp_path):
    conn = _conn()
    save_collection_run(conn, CollectionRun(run_id="run-1"))
    blob_store, capture_repo = (
        FilesystemRawBlobStore(tmp_path, conn),
        SqliteRawCaptureRepository(conn),
    )

    # discovery pass
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
    key = find_by_model_code_and_catalog_id(conn, "S7BC8A", "62184")[0].stable_key()
    assert get_authoritative(conn, key, "run-1") is None

    # first pass with the manifest queued, but the group's page is a
    # deliberate transport failure trap: queue nothing further, so if the
    # driver needed to renavigate SPEC_NAVIGATION it would starve here too;
    # instead we just check the manifest exists after this call and stop
    # short of GROUP_DETAIL by limiting groups to 0.
    t1 = FakeBrowserTransport()
    t1.queue_navigate(_capture(MARKET_INDEX_HTML, MARKET_INDEX_URL))
    t1.queue_navigate(_capture(MANIFEST_HTML, _SPEC_URL))
    run_collection_driver(
        t1,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        market_index_url=MARKET_INDEX_URL,
        filters=OperationalFilters(spec_filter=[key], limit_groups=0),
    )
    manifest = get_authoritative(conn, key, "run-1")
    assert manifest is not None
    assert manifest.expected_group_keys() == frozenset({("front-axle-steering", "407")})

    # second pass: only MARKET_INDEX queued — SPEC_NAVIGATION must NOT be
    # renavigated since the manifest already exists for this (spec_key, run_id).
    t2 = FakeBrowserTransport()
    t2.queue_navigate(_capture(MARKET_INDEX_HTML, MARKET_INDEX_URL))
    run_collection_driver(
        t2,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        market_index_url=MARKET_INDEX_URL,
        filters=OperationalFilters(spec_filter=[key], limit_groups=0),
    )
    assert t2.navigate_calls == [MARKET_INDEX_URL]
