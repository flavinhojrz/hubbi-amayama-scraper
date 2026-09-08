"""T111 — --new-run sobre estado com incompleta compatível: nova execução,
incompleta anterior permanece intocada e retomável depois (DEC-005)."""

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


def test_new_run_leaves_prior_incomplete_run_progress_intact_and_resumable(tmp_path):
    conn = connect(":memory:")
    run_migrations(conn)
    blob_store = FilesystemRawBlobStore(tmp_path, conn)
    capture_repo = SqliteRawCaptureRepository(conn)

    # run-1: discover + manifest + ACCEPT one group, but stop short of a
    # second run (spec stays INCOMPLETE, not VALID, since collection_complete
    # requires the full manifest — this one only has 1 group, so it WOULD go
    # VALID; to keep it genuinely "incomplete progress", we just don't finish
    # discovery for the second spec, leaving run-1 itself incomplete).
    save_collection_run(conn, CollectionRun(run_id="run-1"))
    t1 = FakeBrowserTransport()
    t1.queue_navigate(_capture(MARKET_INDEX_HTML, MARKET_INDEX_URL))
    t1.queue_navigate(_capture(MANIFEST_HTML, _SPEC_URL))
    t1.queue_navigate(_capture(GROUP_HTML, "https://x/front-axle-steering/407"))
    run_collection_driver(
        t1,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        context=AMAROK_CONTEXT,
        filters=OperationalFilters(limit_specs=1),
    )
    key = find_by_model_code_and_catalog_id(conn, "S7BC8A", "62184")[0].stable_key()
    accepted_run1 = get_checkpoint_entry(conn, "run-1", key, "front-axle-steering", "407")
    assert accepted_run1 is not None
    assert accepted_run1.status.value == "ACCEPTED"

    # A brand new run (--new-run) is started, touching only MARKET_INDEX —
    # run-1's checkpoint entry must remain exactly as it was.
    save_collection_run(conn, CollectionRun(run_id="run-2"))
    t2 = FakeBrowserTransport()
    t2.queue_navigate(_capture(MARKET_INDEX_HTML, MARKET_INDEX_URL))
    run_collection_driver(
        t2,
        conn,
        blob_store,
        capture_repo,
        run_id="run-2",
        context=AMAROK_CONTEXT,
        filters=OperationalFilters(limit_specs=0),
    )

    still_there = get_checkpoint_entry(conn, "run-1", key, "front-axle-steering", "407")
    assert still_there == accepted_run1  # byte-for-byte untouched by run-2's existence
