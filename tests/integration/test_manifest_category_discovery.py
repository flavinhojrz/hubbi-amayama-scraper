"""Tests for the category-by-category manifest discovery bug fix (manifest
truncado): a single page (base or one category's own) can no longer, by
itself, mark a manifest `manifest_complete=True` — completeness now requires
visiting and successfully parsing EVERY category declared in the base
page's own nav, each on its own URL
(`orchestration/collection_driver.py::discover_spec_manifest()`).

Root cause (real audit): the Amayama base spec page frequently shows cards
for only a subset of its declared categories — e.g. Saveiro
(VOLKSWAGEN/SAVEIRO/SA-BR, model_code=5X96F4, catalog_id=45297) declared 10
categories but the base page only carried cards for 4 (5 groups) out of a
real universe of 75 groups. The old parser marked that manifest
`manifest_complete=True` anyway (it only checked "≥1 group found").

Covers the acceptance scenarios:
1. base page declares 10 categories, only 4 have cards -> never complete
   from that page alone.
2. all 10 category pages collected -> union of groups, manifest_complete=True.
3. one of the 10 categories fails -> manifest stays incomplete.
8. a CHALLENGE during one category's visit uses the existing challenge
   flow and never produces a false "complete".
9. the same discovery flow works correctly through the worker pool
   (`run_worker_loop()`), not just the legacy `--workers 1` driver.

Fixture: tests/fixtures/spec_navigation/saveiro_base_10_categories_4_with_cards.html
(synthetic, structurally faithful to the real proven selectors and to the
real Saveiro bug report — not a captured real page).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from tests.unit.fakes import FakeBrowserTransport

from amayama_scraper.checkpoint.collection_run import CollectionRun
from amayama_scraper.domain.collection_context import CollectionContext
from amayama_scraper.domain.identity import SpecIdentity
from amayama_scraper.orchestration.collection_driver import (
    OperationalFilters,
    run_collection_driver,
)
from amayama_scraper.orchestration.worker_pool import WorkerPoolConfig, run_worker_loop
from amayama_scraper.parsing.spec_group_manifest import parse_spec_group_manifest
from amayama_scraper.persistence.adapters.filesystem_raw_blob_store import FilesystemRawBlobStore
from amayama_scraper.persistence.adapters.sqlite_raw_capture_repository import (
    SqliteRawCaptureRepository,
)
from amayama_scraper.persistence.db import connect
from amayama_scraper.persistence.migrations.runner import run_migrations
from amayama_scraper.persistence.repositories.checkpoint_repo import save_collection_run
from amayama_scraper.persistence.repositories.manifest_repo import get_authoritative, get_latest
from amayama_scraper.persistence.repositories.spec_registry_repo import save_spec_identity
from amayama_scraper.transport.port import BrowserCapture

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

SAVEIRO_CONTEXT = CollectionContext(
    manufacturer="VOLKSWAGEN", vehicle_model="SAVEIRO", market="SA-BR"
)
_MARKET_INDEX_URL = (
    "https://www.amayama.com/en/genuine-catalogs/epc/volkswagen-overall/saveiro/sa-br"
)
# Empty result set — no market index discovery needed here (the spec is
# registered directly, see _register_saveiro_spec()); only needs to parse
# validly so run_market_index_phase() proceeds (contracts/browser-transport-
# contract.md §3 always runs it first, unconditionally).
_EMPTY_MARKET_INDEX_HTML = """
<html><body>
  <ul class="epcBreadcrumbs">
    <li><div class="breadcrumbs__last-item" dir="auto">SA BR</div></li>
  </ul>
  <div class="epcVariations"><table><tbody></tbody></table></div>
</body></html>
"""

_BASE_URL = (
    "https://www.amayama.com/en/genuine-catalogs/epc/volkswagen-overall/saveiro/sa-br/5x96f4-45297"
)

# Same 10 real category slugs from the bug report.
_DECLARED_CATEGORIES = [
    "access-infotainment-miscell",
    "body",
    "electrics",
    "engine",
    "front-axle-steering",
    "fuel-exhaust-cooling",
    "gearbox",
    "pedals",
    "rear-axle",
    "wheels-brakes",
]

# Already visible on the base page fixture (saveiro_base_10_categories_4_with_cards.html).
_BASE_PAGE_CARDS = {
    "body": [("800", "Body")],
    "engine": [("100", "Base engine")],
    "front-axle-steering": [("407", "Wishbone"), ("409", "Final drive")],
    "wheels-brakes": [("500", "Wheel, tire")],
}

# Only ever visible on each category's OWN page — never on the base page,
# mirroring the real bug (6 of the 10 declared categories had zero cards on
# the base page).
_OWN_PAGE_ONLY_CARDS = {
    "access-infotainment-miscell": [("010", "Access panel")],
    "electrics": [("270", "Wiring harness")],
    "fuel-exhaust-cooling": [("200", "Fuel tank")],
    "gearbox": [("300", "Gearbox housing")],
    "pedals": [("600", "Pedal cluster")],
    "rear-axle": [("450", "Rear axle beam")],
}


def _nav_html() -> str:
    links = [f'<a class="epcVariation__schemaGroup active" data-id="" href="{_BASE_URL}#">All</a>']
    for i, slug in enumerate(_DECLARED_CATEGORIES):
        links.append(
            f'<a class="epcVariation__schemaGroup" data-id="{i}" '
            f'href="{_BASE_URL}/{slug}" title="{slug}">{slug}</a>'
        )
    return '<div class="epcVariation__schemaGroups">' + "\n".join(links) + "</div>"


def _category_page_html(slug: str, cards: list[tuple[str, str]]) -> str:
    """A category's own page: the SAME nav the real site renders on every
    page of a spec (all 10 declared categories) but `.epcVariation__schemas`
    restricted to just this category's own cards."""
    card_html = "".join(
        f"""
      <div class="epcVariation__schema" data-id="{group_id}">
        <div class="epcVariation__schema-name">
          <a href="{_BASE_URL}/{slug}/{group_id}">{group_id} - {title}</a>
        </div>
      </div>"""
        for group_id, title in cards
    )
    return f"""
    <html><body>
      <div class="epcVariation__details">
        <div class="epcVariation__filters">{_nav_html()}</div>
        <div class="epcVariation__schemas">{card_html}</div>
      </div>
    </body></html>
    """


def _all_category_pages() -> dict[str, str]:
    pages = {slug: _category_page_html(slug, cards) for slug, cards in _BASE_PAGE_CARDS.items()}
    pages.update(
        {slug: _category_page_html(slug, cards) for slug, cards in _OWN_PAGE_ONLY_CARDS.items()}
    )
    return pages


def _capture(html: str, url: str) -> BrowserCapture:
    return BrowserCapture(page_source=html, effective_url=url, captured_at=datetime.now(UTC))


def _conn():
    conn = connect(":memory:")
    run_migrations(conn)
    return conn


def _bounded_now(base: datetime, step_seconds: float = 5.0):
    ticks = iter(base + timedelta(seconds=i * step_seconds) for i in range(200))
    return lambda: next(ticks)


def _register_saveiro_spec(conn) -> str:
    return save_spec_identity(
        conn,
        SpecIdentity(
            source="AMAYAMA",
            manufacturer="VOLKSWAGEN",
            vehicle_model="SAVEIRO",
            market="SA-BR",
            model_code="5X96F4",
            amayama_catalog_id="45297",
            production_period_raw="irrelevant for this test",
            source_url=_BASE_URL,
        ),
    )


# --- Scenario 1: base page alone is never authoritative ---------------------


def test_base_page_alone_is_never_complete_even_with_cards_for_a_subset():
    html = (
        FIXTURES / "spec_navigation" / "saveiro_base_10_categories_4_with_cards.html"
    ).read_text(encoding="utf-8")
    result = parse_spec_group_manifest(
        html, spec_key="saveiro-5x96f4-45297", source_capture_id="cap-1"
    )

    assert result.critical_error is None
    manifest = result.manifest
    assert manifest is not None
    assert manifest.manifest_complete is False
    assert len(manifest.categories) == 4
    assert sum(len(c.groups) for c in manifest.categories) == 5

    declared = manifest.validation_evidence["declared_category_urls"]
    assert len(declared) == 10
    assert set(declared) == set(_DECLARED_CATEGORIES)


# --- Scenario 2: all 10 categories visited -> complete union ----------------


def test_all_ten_category_pages_collected_union_is_complete(tmp_path):
    conn = _conn()
    save_collection_run(conn, CollectionRun(run_id="run-1", scope=SAVEIRO_CONTEXT.scope()))
    key = _register_saveiro_spec(conn)
    blob_store = FilesystemRawBlobStore(tmp_path, conn)
    capture_repo = SqliteRawCaptureRepository(conn)

    base_html = (
        FIXTURES / "spec_navigation" / "saveiro_base_10_categories_4_with_cards.html"
    ).read_text(encoding="utf-8")
    category_pages = _all_category_pages()

    transport = FakeBrowserTransport()
    transport.queue_navigate(_capture(_EMPTY_MARKET_INDEX_HTML, _MARKET_INDEX_URL))
    transport.queue_navigate(_capture(base_html, _BASE_URL))
    for slug in sorted(_DECLARED_CATEGORIES):
        transport.queue_navigate(_capture(category_pages[slug], f"{_BASE_URL}/{slug}"))

    run_collection_driver(
        transport,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        context=SAVEIRO_CONTEXT,
        filters=OperationalFilters(spec_filter=[key], limit_groups=0),
        on_event=lambda *a, **kw: None,
    )

    manifest = get_authoritative(conn, key, "run-1")
    assert manifest is not None
    assert manifest.manifest_complete is True
    assert {c.category_slug for c in manifest.categories} == set(_DECLARED_CATEGORIES)

    total_groups = sum(len(c.groups) for c in manifest.categories)
    assert total_groups == 11  # 5 base-visible + 6 own-page-only

    expected = manifest.expected_group_keys()
    assert ("body", "800") in expected
    assert ("front-axle-steering", "407") in expected
    assert ("front-axle-steering", "409") in expected
    assert ("pedals", "600") in expected  # only ever visible on its own page

    evidence = manifest.validation_evidence
    assert evidence["discovery_strategy"] == "category-by-category-v1"
    assert evidence["declared_category_count"] == 10
    assert evidence["visited_category_count"] == 10
    assert evidence["failed_categories"] == {}


# --- CAPTCHA regression: category visits must use the batch-fetch path, ----
# --- exactly like GROUP_DETAIL, when it is enabled --------------------------


def test_category_visits_use_batch_fetch_not_sequential_navigate_when_enabled(tmp_path):
    """Visiting every declared category one navigate() at a time reintroduces
    the near-100% CAPTCHA/challenge rate that GROUP_DETAIL's batch fetch
    (`enable_detail_batch_fetch`, spikes/batched_fetch_spike.py: 0 challenges
    in batch mode vs. ~90-100% with sequential navigate()) exists to avoid —
    a spec with N declared categories used to mean N extra sequential
    navigations. `discover_spec_manifest()` must route ATTEMPTABLE category
    visits through the SAME `navigate_many()` batch path whenever it is
    enabled, never one-by-one `navigate()`."""
    conn = _conn()
    save_collection_run(conn, CollectionRun(run_id="run-1", scope=SAVEIRO_CONTEXT.scope()))
    key = _register_saveiro_spec(conn)
    blob_store = FilesystemRawBlobStore(tmp_path, conn)
    capture_repo = SqliteRawCaptureRepository(conn)

    base_html = (
        FIXTURES / "spec_navigation" / "saveiro_base_10_categories_4_with_cards.html"
    ).read_text(encoding="utf-8")
    category_pages = _all_category_pages()

    transport = FakeBrowserTransport()
    transport.queue_navigate(_capture(_EMPTY_MARKET_INDEX_HTML, _MARKET_INDEX_URL))
    # Bug fix (CAPTCHA excessivo): the base page itself is now ALSO fetched
    # via the batch pre-pass (run_spec_navigation_batch_phase()) before any
    # spec is processed — never a single navigate() when batch fetch is on.
    transport.queue_navigate_many({_BASE_URL: _capture(base_html, _BASE_URL)})
    transport.queue_navigate_many(
        {
            f"{_BASE_URL}/{slug}": _capture(category_pages[slug], f"{_BASE_URL}/{slug}")
            for slug in _DECLARED_CATEGORIES
        }
    )

    run_collection_driver(
        transport,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        context=SAVEIRO_CONTEXT,
        filters=OperationalFilters(spec_filter=[key], limit_groups=0),
        enable_detail_batch_fetch=True,
        on_event=lambda *a, **kw: None,
    )

    # only MARKET_INDEX went through single navigate() — the base page AND
    # all 10 category visits were resolved entirely by batch calls, never
    # one-by-one navigate().
    assert transport.navigate_calls == [_MARKET_INDEX_URL]
    assert len(transport.navigate_many_calls) == 2
    assert transport.navigate_many_calls[0] == [_BASE_URL]
    assert set(transport.navigate_many_calls[1]) == {
        f"{_BASE_URL}/{slug}" for slug in _DECLARED_CATEGORIES
    }

    manifest = get_authoritative(conn, key, "run-1")
    assert manifest is not None
    assert manifest.manifest_complete is True
    assert len(manifest.categories) == 10


# --- Scenario 3: one failing category keeps the manifest incomplete --------


def test_one_failing_category_keeps_manifest_incomplete(tmp_path):
    conn = _conn()
    save_collection_run(conn, CollectionRun(run_id="run-1", scope=SAVEIRO_CONTEXT.scope()))
    key = _register_saveiro_spec(conn)
    blob_store = FilesystemRawBlobStore(tmp_path, conn)
    capture_repo = SqliteRawCaptureRepository(conn)

    base_html = (
        FIXTURES / "spec_navigation" / "saveiro_base_10_categories_4_with_cards.html"
    ).read_text(encoding="utf-8")
    category_pages = _all_category_pages()
    invalid_html = "<html><body><h1>not epc content</h1></body></html>"

    transport = FakeBrowserTransport()
    transport.queue_navigate(_capture(_EMPTY_MARKET_INDEX_HTML, _MARKET_INDEX_URL))
    transport.queue_navigate(_capture(base_html, _BASE_URL))
    for slug in sorted(_DECLARED_CATEGORIES):
        if slug == "pedals":
            transport.queue_navigate(_capture(invalid_html, f"{_BASE_URL}/pedals"))
        else:
            transport.queue_navigate(_capture(category_pages[slug], f"{_BASE_URL}/{slug}"))

    events: list[str] = []
    run_collection_driver(
        transport,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        context=SAVEIRO_CONTEXT,
        filters=OperationalFilters(spec_filter=[key], limit_groups=0),
        on_event=lambda event, **kw: events.append(event),
    )

    # never authoritative — one declared category was never successfully visited.
    assert get_authoritative(conn, key, "run-1") is None

    latest = get_latest(conn, key, "run-1")
    assert latest is not None
    assert latest.manifest_complete is False
    evidence = latest.validation_evidence
    assert evidence["visited_category_count"] == 9
    assert "pedals" in evidence["failed_categories"]
    # the other 9 categories were still visited/recorded — a single failure
    # never aborts discovery of the rest.
    assert set(evidence["visited_categories"]) == set(_DECLARED_CATEGORIES) - {"pedals"}

    assert "SPEC_MANIFEST_CATEGORY_REJECTED" in events
    assert "SPEC_MANIFEST_INCOMPLETE" in events
    assert "SPEC_MANIFEST_COMPLETE" not in events


# --- Scenario 8: CHALLENGE during one category never produces false-complete


def test_challenge_during_one_category_never_produces_false_complete(tmp_path):
    conn = _conn()
    save_collection_run(conn, CollectionRun(run_id="run-1", scope=SAVEIRO_CONTEXT.scope()))
    key = _register_saveiro_spec(conn)
    blob_store = FilesystemRawBlobStore(tmp_path, conn)
    capture_repo = SqliteRawCaptureRepository(conn)

    challenge_html = (FIXTURES / "challenge_cloudflare.html").read_text(encoding="utf-8")
    base_html = (
        FIXTURES / "spec_navigation" / "saveiro_base_10_categories_4_with_cards.html"
    ).read_text(encoding="utf-8")
    category_pages = _all_category_pages()

    transport = FakeBrowserTransport()
    transport.queue_navigate(_capture(_EMPTY_MARKET_INDEX_HTML, _MARKET_INDEX_URL))
    transport.queue_navigate(_capture(base_html, _BASE_URL))
    for slug in sorted(_DECLARED_CATEGORIES):
        if slug == "gearbox":
            transport.queue_navigate(_capture(challenge_html, f"{_BASE_URL}/gearbox"))
        else:
            transport.queue_navigate(_capture(category_pages[slug], f"{_BASE_URL}/{slug}"))
    # "gearbox" never resolves — the existing challenge-poll loop (generic,
    # capture_kind-agnostic) is used exactly as it is for SPEC_NAVIGATION/
    # GROUP_DETAIL; it eventually times out.
    for _ in range(50):
        transport.queue_current_capture(_capture(challenge_html, f"{_BASE_URL}/gearbox"))

    events: list[str] = []
    run_collection_driver(
        transport,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        context=SAVEIRO_CONTEXT,
        filters=OperationalFilters(spec_filter=[key], limit_groups=0),
        poll_interval=0.0,
        sleep=lambda _s: None,
        challenge_timeout=10.0,
        now=_bounded_now(datetime(2026, 9, 10, tzinfo=UTC)),
        on_event=lambda event, **kw: events.append(event),
    )

    assert "CHALLENGE_WAITING" in events
    assert "SPEC_MANIFEST_CATEGORY_CHALLENGE_TIMEOUT" in events

    # never falsely marked complete — CHALLENGE never resolved for "gearbox".
    assert get_authoritative(conn, key, "run-1") is None
    latest = get_latest(conn, key, "run-1")
    assert latest is not None
    assert latest.manifest_complete is False
    assert "gearbox" in latest.validation_evidence["failed_categories"]
    # the remaining categories (after "gearbox" alphabetically) were still
    # attempted — a stuck challenge on one category never aborts the rest.
    assert {"pedals", "rear-axle", "wheels-brakes"} <= set(
        latest.validation_evidence["visited_categories"]
    )


# --- Scenario 9: worker pool compatibility -----------------------------------


def test_discovery_completes_correctly_through_the_worker_pool(tmp_path):
    conn = _conn()
    save_collection_run(conn, CollectionRun(run_id="run-1", scope=SAVEIRO_CONTEXT.scope()))
    key = _register_saveiro_spec(conn)
    blob_store = FilesystemRawBlobStore(tmp_path, conn)
    capture_repo = SqliteRawCaptureRepository(conn)

    base_html = (
        FIXTURES / "spec_navigation" / "saveiro_base_10_categories_4_with_cards.html"
    ).read_text(encoding="utf-8")
    category_pages = _all_category_pages()

    # run_worker_loop() never runs MARKET_INDEX itself (that is the
    # orchestrator's job, once, in run_pool() — contracts/worker-pool-
    # contract.md §1); only the spec-level discovery is exercised here.
    transport = FakeBrowserTransport()
    transport.queue_navigate(_capture(base_html, _BASE_URL))
    for slug in sorted(_DECLARED_CATEGORIES):
        transport.queue_navigate(_capture(category_pages[slug], f"{_BASE_URL}/{slug}"))

    run_worker_loop(
        transport,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        context=SAVEIRO_CONTEXT,
        worker_id="worker-0",
        filters=OperationalFilters(spec_filter=[key], limit_groups=0),
        pool_config=WorkerPoolConfig(workers=1),
        pool_session_id="test-session",
        sleep=lambda _s: None,
    )

    manifest = get_authoritative(conn, key, "run-1")
    assert manifest is not None
    assert manifest.manifest_complete is True
    assert len(manifest.categories) == 10
    assert sum(len(c.groups) for c in manifest.categories) == 11
