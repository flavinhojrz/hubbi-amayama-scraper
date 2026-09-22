"""Repair/backfill (bug fix — manifest truncado): `OperationalFilters.
force_manifest_rediscovery` + `force` — reused by `cli/main.py::_run_repair()`
(`--repair-manifest`) — forces a spec whose manifest was already saved
`manifest_complete=True` under the OLD (buggy, single-page) parser to be
rediscovered category-by-category under the SAME `run_id`, without ever
touching groups already `ACCEPTED`.

Covers the acceptance scenarios:
5. a group already ACCEPTED before repair is never reprocessed/renavigated.
6. a newly-discovered group (missing from the old manifest) becomes pending
   work and gets collected.
7. running repair twice is idempotent — no duplicate checkpoints/category
   visits, and the second pass never renavigates anything for the spec.

The "old buggy" starting state (manifest_complete=True with only 1 of the 2
real categories) can no longer be produced by the current parser (that is
the bug being fixed) — it is seeded directly via `save_manifest()`, exactly
representing what is already sitting in a pre-fix `amayama.db`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from tests.support import AMAROK_CONTEXT
from tests.unit.fakes import FakeBrowserTransport

from amayama_scraper.checkpoint.collection_run import CollectionRun
from amayama_scraper.domain.identity import SpecIdentity
from amayama_scraper.domain.manifest import ManifestCategory, ManifestGroupRef, SpecGroupManifest
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
    list_accepted,
    save_collection_run,
)
from amayama_scraper.persistence.repositories.current_state_repo import get_current_state
from amayama_scraper.persistence.repositories.manifest_repo import get_authoritative, save_manifest
from amayama_scraper.persistence.repositories.spec_registry_repo import save_spec_identity
from amayama_scraper.snapshots.snapshot import SnapshotState
from amayama_scraper.transport.port import BrowserCapture

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
MARKET_INDEX_URL = (
    "https://www.amayama.com/en/genuine-catalogs/epc/volkswagen-overall/amarok/ama-br"
)
_EMPTY_MARKET_INDEX_HTML = """
<html><body>
  <ul class="epcBreadcrumbs">
    <li><div class="breadcrumbs__last-item" dir="auto">AMA BR</div></li>
  </ul>
  <div class="epcVariations"><table><tbody></tbody></table></div>
</body></html>
"""

_BASE_URL = "https://x/repair-spec-1"
_OLD_GROUP_URL = "https://x/front-axle-steering/407"
_NEW_CATEGORY_URL = "https://x/engine"
_NEW_GROUP_URL = "https://x/engine/100"

_OLD_GROUP_HTML = """
<html><body><div class="epcVariation__details"><div class="epcSchema__schemas">
  <div class="epcSchema__schema" data-id="SCH-1"><table class="entriesTable">
    <tr data-key="A01"><td class="entriesTable__number">1K0407151</td>
    <td class="entriesTable__description">Control arm</td>
    <td class="entriesTable__period">08.2010-12.2015</td>
    <td class="entriesTable__required">1</td></tr>
  </table></div>
</div></div></body></html>
"""

_NEW_GROUP_HTML = """
<html><body><div class="epcVariation__details"><div class="epcSchema__schemas">
  <div class="epcSchema__schema" data-id="SCH-2"><table class="entriesTable">
    <tr data-key="A01"><td class="entriesTable__number">06L100175</td>
    <td class="entriesTable__description">Base engine</td>
    <td class="entriesTable__period">08.2010-12.2015</td>
    <td class="entriesTable__required">1</td></tr>
  </table></div>
</div></div></body></html>
"""


def _capture(html: str, url: str) -> BrowserCapture:
    return BrowserCapture(page_source=html, effective_url=url, captured_at=datetime.now(UTC))


def _repair_base_page_html() -> str:
    """The corrected base page: declares the SAME old category
    (front-axle-steering) plus a NEW one (engine) the buggy manifest never
    knew about — neither category's cards are shown here (the whole point
    of the fix: every declared category must be visited on its own URL)."""
    return f"""
    <html><body>
      <div class="epcVariation__details">
        <div class="epcVariation__filters">
          <div class="epcVariation__schemaGroups">
            <a class="epcVariation__schemaGroup active" data-id="" href="{_BASE_URL}#">All</a>
            <a class="epcVariation__schemaGroup" data-id="4" href="https://x/front-axle-steering">FA</a>
            <a class="epcVariation__schemaGroup" data-id="1" href="{_NEW_CATEGORY_URL}">Engine</a>
          </div>
        </div>
        <div class="epcVariation__schemas"></div>
      </div>
    </body></html>
    """


def _category_page_html(*, cards: list[tuple[str, str, str]]) -> str:
    """One category's own page: same nav as the base page, `.epcVariation__schemas`
    restricted to its own card(s). `cards` is a list of (group_id, category_slug, url)."""
    card_html = "".join(
        f"""
      <div class="epcVariation__schema" data-id="{group_id}">
        <div class="epcVariation__schema-name"><a href="{url}">{group_id}</a></div>
      </div>"""
        for group_id, _slug, url in cards
    )
    return f"""
    <html><body>
      <div class="epcVariation__details">
        <div class="epcVariation__filters">
          <div class="epcVariation__schemaGroups">
            <a class="epcVariation__schemaGroup active" data-id="" href="{_BASE_URL}#">All</a>
            <a class="epcVariation__schemaGroup" data-id="4" href="https://x/front-axle-steering">FA</a>
            <a class="epcVariation__schemaGroup" data-id="1" href="{_NEW_CATEGORY_URL}">Engine</a>
          </div>
        </div>
        <div class="epcVariation__schemas">{card_html}</div>
      </div>
    </body></html>
    """


def _conn():
    conn = connect(":memory:")
    run_migrations(conn)
    return conn


def _seed_old_buggy_state(conn, blob_store, capture_repo, key: str) -> None:
    """Reproduces exactly what a pre-fix `amayama.db` has for a truncated
    spec: `manifest_complete=True` covering only 1 of the real 2 categories
    (the parser can no longer produce this — see module docstring), plus a
    real ACCEPTED checkpoint/VALID snapshot for that one group, obtained by
    actually running the (legacy, non-repair) driver against it."""
    old_manifest = SpecGroupManifest(
        spec_key=key,
        source_capture_id="cap-old-nav",
        discovered_at=datetime.now(UTC),
        categories=(
            ManifestCategory(
                category_slug="front-axle-steering",
                groups=(ManifestGroupRef(group_id="407", source_url=_OLD_GROUP_URL),),
            ),
        ),
        manifest_complete=True,  # the bug: true from a single page, no "discovery_strategy"
        validation_evidence={"category_count": 1, "group_count": 1},
    )
    save_manifest(conn, old_manifest, run_id="run-1")

    # Normal (non-repair) collection pass: get_authoritative() already
    # returns the old manifest (manifest_complete=True), so no rediscovery
    # is attempted — only the one expected group is fetched.
    transport = FakeBrowserTransport()
    transport.queue_navigate(_capture(_EMPTY_MARKET_INDEX_HTML, MARKET_INDEX_URL))
    transport.queue_navigate(_capture(_OLD_GROUP_HTML, _OLD_GROUP_URL))
    run_collection_driver(
        transport,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        context=AMAROK_CONTEXT,
        filters=OperationalFilters(spec_filter=[key]),
        on_event=lambda *a, **kw: None,
    )


def test_repair_preserves_accepted_discovers_new_pending_and_is_idempotent(tmp_path):
    conn = _conn()
    save_collection_run(conn, CollectionRun(run_id="run-1", scope=AMAROK_CONTEXT.scope()))
    key = save_spec_identity(
        conn,
        SpecIdentity(
            source="AMAYAMA",
            manufacturer="VOLKSWAGEN",
            vehicle_model="AMAROK",
            market="AMA-BR",
            model_code="REPAIR1",
            amayama_catalog_id="900001",
            production_period_raw="irrelevant for this test",
            source_url=_BASE_URL,
        ),
    )
    blob_store = FilesystemRawBlobStore(tmp_path, conn)
    capture_repo = SqliteRawCaptureRepository(conn)

    _seed_old_buggy_state(conn, blob_store, capture_repo, key)

    # setup sanity: old (buggy) state is VALID with exactly 1 ACCEPTED group.
    assert get_current_state(conn, key) is not None
    accepted_before = list_accepted(conn, "run-1", key)
    assert len(accepted_before) == 1
    assert (accepted_before[0].category_slug, accepted_before[0].group_id) == (
        "front-axle-steering",
        "407",
    )

    # --- Repair pass 1 -------------------------------------------------
    # Base page now declares BOTH categories; neither's cards on the base
    # page itself (bug fix: every category must be visited on its own URL).
    # front-axle-steering's own page repeats the ALREADY-KNOWN group 407 —
    # its GROUP_DETAIL must never be renavigated (scenario 5); engine's own
    # page reveals the NEW group 100 (scenario 6), which IS fetched.
    # discover_spec_manifest() visits declared categories in SORTED order —
    # "engine" < "front-axle-steering" alphabetically — so the fake's FIFO
    # queue must offer engine's own page first, then front-axle-steering's.
    repair_transport_1 = FakeBrowserTransport()
    repair_transport_1.queue_navigate(_capture(_EMPTY_MARKET_INDEX_HTML, MARKET_INDEX_URL))
    repair_transport_1.queue_navigate(_capture(_repair_base_page_html(), _BASE_URL))
    repair_transport_1.queue_navigate(
        _capture(
            _category_page_html(cards=[("100", "engine", _NEW_GROUP_URL)]),
            _NEW_CATEGORY_URL,
        )
    )
    repair_transport_1.queue_navigate(
        _capture(
            _category_page_html(cards=[("407", "front-axle-steering", _OLD_GROUP_URL)]),
            "https://x/front-axle-steering",
        )
    )
    repair_transport_1.queue_navigate(_capture(_NEW_GROUP_HTML, _NEW_GROUP_URL))

    all_specs_force = [key]
    events_1: list[str] = []
    run_collection_driver(
        repair_transport_1,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        context=AMAROK_CONTEXT,
        filters=OperationalFilters(
            spec_filter=[key], force=all_specs_force, force_manifest_rediscovery=True
        ),
        on_event=lambda event, **kw: events_1.append(event),
    )

    # scenario 5: group 407 was never renavigated — the fake transport only
    # ever had ONE response queued for it (consumed during the old/buggy
    # pass); if the repair pass had tried to fetch it again the queue would
    # have starved with an AssertionError, which it did not.
    assert _OLD_GROUP_URL not in repair_transport_1.navigate_calls[2:]

    manifest_after_repair = get_authoritative(conn, key, "run-1")
    assert manifest_after_repair is not None
    assert manifest_after_repair.manifest_complete is True
    assert {c.category_slug for c in manifest_after_repair.categories} == {
        "front-axle-steering",
        "engine",
    }
    assert manifest_after_repair.expected_group_keys() == frozenset(
        {("front-axle-steering", "407"), ("engine", "100")}
    )

    # scenario 5 (again, from the durable state): the old checkpoint is
    # untouched — still ACCEPTED, same as before repair.
    accepted_after = {(e.category_slug, e.group_id): e for e in list_accepted(conn, "run-1", key)}
    assert accepted_after[("front-axle-steering", "407")] == accepted_before[0]

    # scenario 6: the newly-discovered group became pending work and got
    # collected in this same repair pass.
    assert ("engine", "100") in accepted_after
    assert "GROUP_ACCEPTED" in events_1

    current_after_repair = get_current_state(conn, key)
    assert current_after_repair is not None
    from amayama_scraper.persistence.repositories.snapshot_repo import get_snapshot

    snapshot_after_repair = get_snapshot(conn, current_after_repair.latest_snapshot_id)
    assert snapshot_after_repair is not None
    assert snapshot_after_repair.state == SnapshotState.VALID

    checkpoint_count_after_pass_1 = conn.execute(
        "SELECT COUNT(*) AS c FROM checkpoint_entry WHERE run_id = 'run-1' AND spec_key = ?",
        (key,),
    ).fetchone()["c"]
    visit_count_after_pass_1 = conn.execute(
        "SELECT COUNT(*) AS c FROM spec_category_visit WHERE run_id = 'run-1' AND spec_key = ?",
        (key,),
    ).fetchone()["c"]
    assert checkpoint_count_after_pass_1 == 2  # 407 + 100, never duplicated
    assert visit_count_after_pass_1 == 2  # front-axle-steering + engine

    # --- Repair pass 2 (idempotency, scenario 7) ------------------------
    # The manifest is already `manifest_complete=True` AND carries the new
    # discovery_strategy marker — a second repair pass must recognize this
    # and skip rediscovery entirely for this spec (only MARKET_INDEX is
    # queued; any attempt to renavigate anything else would starve the fake).
    repair_transport_2 = FakeBrowserTransport()
    repair_transport_2.queue_navigate(_capture(_EMPTY_MARKET_INDEX_HTML, MARKET_INDEX_URL))
    run_collection_driver(
        repair_transport_2,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        context=AMAROK_CONTEXT,
        filters=OperationalFilters(
            spec_filter=[key], force=all_specs_force, force_manifest_rediscovery=True
        ),
        on_event=lambda *a, **kw: None,
    )
    assert repair_transport_2.navigate_calls == [MARKET_INDEX_URL]

    checkpoint_count_after_pass_2 = conn.execute(
        "SELECT COUNT(*) AS c FROM checkpoint_entry WHERE run_id = 'run-1' AND spec_key = ?",
        (key,),
    ).fetchone()["c"]
    visit_count_after_pass_2 = conn.execute(
        "SELECT COUNT(*) AS c FROM spec_category_visit WHERE run_id = 'run-1' AND spec_key = ?",
        (key,),
    ).fetchone()["c"]
    assert checkpoint_count_after_pass_2 == checkpoint_count_after_pass_1  # no duplicates
    assert visit_count_after_pass_2 == visit_count_after_pass_1  # no duplicates

    manifest_after_pass_2 = get_authoritative(conn, key, "run-1")
    assert manifest_after_pass_2 is not None
    assert (
        manifest_after_pass_2.expected_group_keys() == manifest_after_repair.expected_group_keys()
    )
