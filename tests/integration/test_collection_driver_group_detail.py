"""T082/T083 — laço de nível C (GROUP_DETAIL): itera get_pending_groups()
real, resolve source_url via o manifesto, classifica cada unidade antes de
decidir capturar (FR-008, US2 cenário 2). Nenhum grupo fora do manifesto é
navegado; REQUIRES_EXPLICIT_RETRY sem --retry-rejected é pulado."""

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
from amayama_scraper.persistence.repositories.checkpoint_repo import (
    get_checkpoint_entry,
    save_collection_run,
)
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

# Manifest with TWO groups so we can exercise "one accepted, one rejected".
MANIFEST_HTML = """
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

INVALID_GROUP_HTML = "<html><body><h1>not epc content</h1></body></html>"


def _capture(html: str, url: str) -> BrowserCapture:
    return BrowserCapture(page_source=html, effective_url=url, captured_at=datetime.now(UTC))


def _conn():
    conn = connect(":memory:")
    run_migrations(conn)
    return conn


def test_only_manifest_groups_are_navigated_and_rejection_is_not_retried_automatically(tmp_path):
    conn = _conn()
    save_collection_run(conn, CollectionRun(run_id="run-1"))
    blob_store, capture_repo = (
        FilesystemRawBlobStore(tmp_path, conn),
        SqliteRawCaptureRepository(conn),
    )

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

    # Pass 1: manifest + one valid group (front-axle-steering/407) + one
    # invalid group (engine/100). get_pending_groups() returns units sorted
    # by (category_slug, group_id), so "engine" is visited before
    # "front-axle-steering" — queue order must match that processing order,
    # not manifest declaration order (the fake is a plain FIFO queue, blind
    # to which URL was actually requested).
    t1 = FakeBrowserTransport()
    t1.queue_navigate(_capture(MARKET_INDEX_HTML, MARKET_INDEX_URL))
    t1.queue_navigate(_capture(MANIFEST_HTML, _SPEC_URL))
    t1.queue_navigate(_capture(INVALID_GROUP_HTML, "https://x/engine/100"))
    t1.queue_navigate(_capture(VALID_GROUP_HTML, "https://x/front-axle-steering/407"))
    run_collection_driver(
        t1,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        market_index_url=MARKET_INDEX_URL,
        filters=OperationalFilters(spec_filter=[key]),
    )

    accepted = get_checkpoint_entry(conn, "run-1", key, "front-axle-steering", "407")
    rejected = get_checkpoint_entry(conn, "run-1", key, "engine", "100")
    assert accepted is not None and accepted.status.value == "ACCEPTED"
    assert rejected is not None and rejected.status.value == "REJECTED"

    # exactly the two manifest URLs were navigated for GROUP_DETAIL — never
    # anything outside the manifest.
    group_calls = [u for u in t1.navigate_calls if u not in (MARKET_INDEX_URL, _SPEC_URL)]
    assert set(group_calls) == {"https://x/front-axle-steering/407", "https://x/engine/100"}

    # Pass 2: no --retry-rejected — the rejected group must NOT be renavigated.
    t2 = FakeBrowserTransport()
    t2.queue_navigate(_capture(MARKET_INDEX_HTML, MARKET_INDEX_URL))
    run_collection_driver(
        t2,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        market_index_url=MARKET_INDEX_URL,
        filters=OperationalFilters(spec_filter=[key]),
    )
    assert t2.navigate_calls == [
        MARKET_INDEX_URL
    ]  # manifest already exists, no pending ACCEPTED group left to retry automatically

    # Pass 3: --retry-rejected explicitly retries the rejected unit, now with a valid page.
    t3 = FakeBrowserTransport()
    t3.queue_navigate(_capture(MARKET_INDEX_HTML, MARKET_INDEX_URL))
    t3.queue_navigate(
        _capture(VALID_GROUP_HTML.replace("1K0407151", "1K0407152"), "https://x/engine/100")
    )
    run_collection_driver(
        t3,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        market_index_url=MARKET_INDEX_URL,
        filters=OperationalFilters(spec_filter=[key], retry_rejected=True),
    )
    retried = get_checkpoint_entry(conn, "run-1", key, "engine", "100")
    assert retried is not None and retried.status.value == "ACCEPTED"
