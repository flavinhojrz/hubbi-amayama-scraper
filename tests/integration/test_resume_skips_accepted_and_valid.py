"""T078/T114 — quickstart.md Cenário 6 / FR-018 / SC-003 / SC-004: um
`Group` `ACCEPTED` numa passada anterior não é renavegado numa passada
seguinte (mesmo `run_id`); uma spec com `CurrentSpecState`/`SpecSnapshot`
já `VALID` é ignorada por completo — a menos que `--force` a inclua
explicitamente."""

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


def test_valid_spec_is_skipped_entirely_on_a_later_invocation(tmp_path):
    conn = connect(":memory:")
    run_migrations(conn)
    save_collection_run(conn, CollectionRun(run_id="run-1"))
    blob_store = FilesystemRawBlobStore(tmp_path, conn)
    capture_repo = SqliteRawCaptureRepository(conn)

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
    assert get_current_state(conn, key) is not None

    # A later invocation (same run_id, resume semantics): only MARKET_INDEX
    # is queued — if the VALID spec were renavigated at all (SPEC_NAVIGATION
    # or GROUP_DETAIL), the fake would starve.
    t2 = FakeBrowserTransport()
    t2.queue_navigate(_capture(MARKET_INDEX_HTML, MARKET_INDEX_URL))
    run_collection_driver(
        t2,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        context=AMAROK_CONTEXT,
        filters=OperationalFilters(spec_filter=[key]),
    )
    assert t2.navigate_calls == [MARKET_INDEX_URL]


def test_accepted_group_is_not_renavigated_in_a_later_pass_of_the_same_spec(tmp_path):
    """Two-group manifest: group A gets ACCEPTED in pass 1; pass 2 (same
    run_id) must only (re)navigate group B, never re-touch A."""
    conn = connect(":memory:")
    run_migrations(conn)
    save_collection_run(conn, CollectionRun(run_id="run-1"))
    blob_store = FilesystemRawBlobStore(tmp_path, conn)
    capture_repo = SqliteRawCaptureRepository(conn)

    two_group_manifest = MANIFEST_HTML.replace(
        '<a class="epcVariation__schemaGroup" data-id="4" href="https://x/front-axle-steering">FA</a>',
        '<a class="epcVariation__schemaGroup" data-id="4" href="https://x/front-axle-steering">FA</a>'
        '\n        <a class="epcVariation__schemaGroup" data-id="1" href="https://x/engine">EN</a>',
    ).replace(
        '<div class="epcVariation__schema" data-id="407">\n'
        '        <div class="epcVariation__schema-name"><a href="https://x/front-axle-steering/407">407</a></div>\n'
        "      </div>",
        '<div class="epcVariation__schema" data-id="407">\n'
        '        <div class="epcVariation__schema-name"><a href="https://x/front-axle-steering/407">407</a></div>\n'
        "      </div>\n"
        '      <div class="epcVariation__schema" data-id="100">\n'
        '        <div class="epcVariation__schema-name"><a href="https://x/engine/100">100</a></div>\n'
        "      </div>",
    )

    # get_pending_groups() sorts (category_slug, group_id): "engine" is
    # visited before "front-axle-steering" — limit_groups=1 accepts only
    # engine/100 in pass 1.
    t1 = FakeBrowserTransport()
    t1.queue_navigate(_capture(MARKET_INDEX_HTML, MARKET_INDEX_URL))
    t1.queue_navigate(_capture(two_group_manifest, _SPEC_URL))
    t1.queue_navigate(_capture(GROUP_HTML, "https://x/engine/100"))
    run_collection_driver(
        t1,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        context=AMAROK_CONTEXT,
        filters=OperationalFilters(limit_specs=1, limit_groups=1),
    )
    key = find_by_model_code_and_catalog_id(conn, "S7BC8A", "62184")[0].stable_key()

    # Pass 2 (same run_id): only the remaining group (front-axle-steering/407)
    # should be navigated — engine/100 (already ACCEPTED) must not reappear.
    t2 = FakeBrowserTransport()
    t2.queue_navigate(_capture(MARKET_INDEX_HTML, MARKET_INDEX_URL))
    t2.queue_navigate(
        _capture(GROUP_HTML.replace("1K0407151", "1K0407152"), "https://x/front-axle-steering/407")
    )
    run_collection_driver(
        t2,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        context=AMAROK_CONTEXT,
        filters=OperationalFilters(spec_filter=[key]),
    )
    group_level_calls = [u for u in t2.navigate_calls if u != MARKET_INDEX_URL]
    assert group_level_calls == ["https://x/front-axle-steering/407"]
