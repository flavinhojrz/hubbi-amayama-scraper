"""T112 — quickstart.md Cenário 3 / FR-020 / SC-011: uma rejeição de
validação (INVALID/INCOMPLETE/TRANSLATION_CONTAMINATED) permanece REJECTED
através de N passadas sucessivas do driver sem `--retry-rejected`, com
`attempt_count == 1` (uma única tentativa real) — e só é retentada na
passada com a flag explícita (DEC-006)."""

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

INVALID_GROUP_HTML = "<html><body><h1>not epc content</h1></body></html>"
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


def test_rejected_group_survives_n_passes_unretried_then_retried_explicitly(tmp_path):
    conn = connect(":memory:")
    run_migrations(conn)
    save_collection_run(conn, CollectionRun(run_id="run-1"))
    blob_store = FilesystemRawBlobStore(tmp_path, conn)
    capture_repo = SqliteRawCaptureRepository(conn)

    # Pass 1: manifest + INVALID group -> REJECTED, attempt_count == 1.
    t1 = FakeBrowserTransport()
    t1.queue_navigate(_capture(MARKET_INDEX_HTML, MARKET_INDEX_URL))
    t1.queue_navigate(_capture(MANIFEST_HTML, _SPEC_URL))
    t1.queue_navigate(_capture(INVALID_GROUP_HTML, "https://x/front-axle-steering/407"))
    run_collection_driver(
        t1,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        market_index_url=MARKET_INDEX_URL,
        filters=OperationalFilters(limit_specs=1),
    )
    key = find_by_model_code_and_catalog_id(conn, "S7BC8A", "62184")[0].stable_key()
    entry = get_checkpoint_entry(conn, "run-1", key, "front-axle-steering", "407")
    assert entry is not None
    assert entry.status.value == "REJECTED"
    assert entry.attempt_count == 1

    # Passes 2 and 3 WITHOUT --retry-rejected: only MARKET_INDEX is queued —
    # if the driver attempted to renavigate the rejected group, the fake
    # would starve (AssertionError) since no group capture is queued.
    for _ in range(2):
        t_n = FakeBrowserTransport()
        t_n.queue_navigate(_capture(MARKET_INDEX_HTML, MARKET_INDEX_URL))
        run_collection_driver(
            t_n,
            conn,
            blob_store,
            capture_repo,
            run_id="run-1",
            market_index_url=MARKET_INDEX_URL,
            filters=OperationalFilters(spec_filter=[key]),
        )
        unchanged = get_checkpoint_entry(conn, "run-1", key, "front-axle-steering", "407")
        assert unchanged.attempt_count == 1  # never retried automatically
        assert unchanged.status.value == "REJECTED"

    # Pass 4 WITH --retry-rejected: now the group IS retried, this time valid.
    t_retry = FakeBrowserTransport()
    t_retry.queue_navigate(_capture(MARKET_INDEX_HTML, MARKET_INDEX_URL))
    t_retry.queue_navigate(_capture(VALID_GROUP_HTML, "https://x/front-axle-steering/407"))
    run_collection_driver(
        t_retry,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        market_index_url=MARKET_INDEX_URL,
        filters=OperationalFilters(spec_filter=[key], retry_rejected=True),
    )
    retried = get_checkpoint_entry(conn, "run-1", key, "front-axle-steering", "407")
    assert retried.status.value == "ACCEPTED"
    assert retried.attempt_count == 2  # the original attempt + the explicit retry
