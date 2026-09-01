"""Blocker 2 (Codex) — CollectionRun.completed_at é marcado somente quando
a coleta termina normalmente e TODAS as specs conhecidas alcançam
VALID/STALE (data-model.md §11, DEC-005/FR-019). Reaproveita o lifecycle
já existente de CollectionRun (save_collection_run já faz upsert de
completed_at) — nenhuma entidade nova, nenhuma migration.
"""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime
from pathlib import Path

from tests.unit.fakes import FakeBrowserTransport

from amayama_scraper.checkpoint.collection_run import FIXED_SCOPE, CollectionRun
from amayama_scraper.orchestration.collection_driver import (
    OperationalFilters,
    run_collection_driver,
)
from amayama_scraper.orchestration.run_selection import select_run
from amayama_scraper.persistence.adapters.filesystem_raw_blob_store import FilesystemRawBlobStore
from amayama_scraper.persistence.adapters.sqlite_raw_capture_repository import (
    SqliteRawCaptureRepository,
)
from amayama_scraper.persistence.db import connect
from amayama_scraper.persistence.migrations.runner import run_migrations
from amayama_scraper.persistence.repositories.checkpoint_repo import (
    get_collection_run,
    list_incomplete_runs,
    save_collection_run,
)
from amayama_scraper.persistence.repositories.spec_registry_repo import (
    find_by_model_code_and_catalog_id,
)
from amayama_scraper.transport.port import BrowserCapture

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

# Single-spec market index fixture (one discovered spec only, so a full
# unfiltered pass can legitimately reach "all known specs VALID").
SINGLE_SPEC_MARKET_INDEX_HTML = (FIXTURES / "market_index" / "open_ended_period.html").read_text(
    encoding="utf-8"
)
TWO_SPEC_MARKET_INDEX_HTML = (
    FIXTURES / "market_index" / "same_model_code_diff_catalog.html"
).read_text(encoding="utf-8")
MARKET_INDEX_URL = (
    "https://www.amayama.com/en/genuine-catalogs/epc/volkswagen-overall/amarok/ama-br"
)
_URL_62184 = (
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

INVALID_GROUP_HTML = "<html><body><h1>not epc content</h1></body></html>"


def _capture(html: str, url: str) -> BrowserCapture:
    return BrowserCapture(page_source=html, effective_url=url, captured_at=datetime.now(UTC))


def _conn():
    conn = connect(":memory:")
    run_migrations(conn)
    return conn


def _spec_url_from_fixture() -> str:
    # valid_multi_entry.html's single entry's own href-derived URL.
    from amayama_scraper.parsing.market_index import parse_market_spec_index

    result = parse_market_spec_index(SINGLE_SPEC_MARKET_INDEX_HTML, source_capture_id="cap-x")
    assert result.entries, "fixture must contain at least one spec entry"
    return result.entries[0].source_url


# --- Cenário 1: run completa normalmente -------------------------------


def test_run_completes_normally_and_stops_appearing_in_incomplete_runs(tmp_path):
    conn = _conn()
    save_collection_run(conn, CollectionRun(run_id="run-1"))
    blob_store = FilesystemRawBlobStore(tmp_path, conn)
    capture_repo = SqliteRawCaptureRepository(conn)
    spec_url = _spec_url_from_fixture()

    transport = FakeBrowserTransport()
    transport.queue_navigate(_capture(SINGLE_SPEC_MARKET_INDEX_HTML, MARKET_INDEX_URL))
    transport.queue_navigate(_capture(MANIFEST_HTML, spec_url))
    transport.queue_navigate(_capture(GROUP_HTML, "https://x/front-axle-steering/407"))

    run_collection_driver(
        transport,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        market_index_url=MARKET_INDEX_URL,
        filters=OperationalFilters(),  # unfiltered — the whole known scope
    )

    run = get_collection_run(conn, "run-1")
    assert run is not None
    assert run.completed_at is not None
    assert list_incomplete_runs(conn, FIXED_SCOPE) == []


def test_subsequent_invocation_without_flags_creates_a_new_run_after_completion(tmp_path):
    conn = _conn()
    save_collection_run(conn, CollectionRun(run_id="run-1"))
    blob_store = FilesystemRawBlobStore(tmp_path, conn)
    capture_repo = SqliteRawCaptureRepository(conn)
    spec_url = _spec_url_from_fixture()

    transport = FakeBrowserTransport()
    transport.queue_navigate(_capture(SINGLE_SPEC_MARKET_INDEX_HTML, MARKET_INDEX_URL))
    transport.queue_navigate(_capture(MANIFEST_HTML, spec_url))
    transport.queue_navigate(_capture(GROUP_HTML, "https://x/front-axle-steering/407"))
    run_collection_driver(
        transport,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        market_index_url=MARKET_INDEX_URL,
        filters=OperationalFilters(),
    )

    selection = select_run(
        resume_run_id=None,
        new_run=False,
        scope=FIXED_SCOPE,
        now=datetime.now(UTC),
        run_id_factory=lambda: "run-2",
        get_collection_run=lambda rid: get_collection_run(conn, rid),
        list_incomplete_runs=lambda scope: list_incomplete_runs(conn, scope),
        save_collection_run=lambda run: save_collection_run(conn, run),
    )
    assert selection.created_new is True
    assert selection.run.run_id == "run-2"


# --- Cenário 2: run interrompida/com trabalho pendente ------------------


def test_run_with_rejected_group_stays_incomplete(tmp_path):
    conn = _conn()
    save_collection_run(conn, CollectionRun(run_id="run-1"))
    blob_store = FilesystemRawBlobStore(tmp_path, conn)
    capture_repo = SqliteRawCaptureRepository(conn)
    spec_url = _spec_url_from_fixture()

    transport = FakeBrowserTransport()
    transport.queue_navigate(_capture(SINGLE_SPEC_MARKET_INDEX_HTML, MARKET_INDEX_URL))
    transport.queue_navigate(_capture(MANIFEST_HTML, spec_url))
    transport.queue_navigate(_capture(INVALID_GROUP_HTML, "https://x/front-axle-steering/407"))

    run_collection_driver(
        transport,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        market_index_url=MARKET_INDEX_URL,
        filters=OperationalFilters(),
    )

    run = get_collection_run(conn, "run-1")
    assert run is not None
    assert run.completed_at is None
    assert [r.run_id for r in list_incomplete_runs(conn, FIXED_SCOPE)] == ["run-1"]


def test_run_interrupted_by_exception_mid_loop_stays_incomplete(tmp_path):
    conn = _conn()
    save_collection_run(conn, CollectionRun(run_id="run-1"))
    blob_store = FilesystemRawBlobStore(tmp_path, conn)
    capture_repo = SqliteRawCaptureRepository(conn)

    transport = FakeBrowserTransport()
    transport.queue_navigate(RuntimeError("simulated hard navigation failure"))

    with contextlib.suppress(RuntimeError):
        run_collection_driver(
            transport,
            conn,
            blob_store,
            capture_repo,
            run_id="run-1",
            market_index_url=MARKET_INDEX_URL,
            filters=OperationalFilters(),
        )

    run = get_collection_run(conn, "run-1")
    assert run is not None
    assert run.completed_at is None
    assert [r.run_id for r in list_incomplete_runs(conn, FIXED_SCOPE)] == ["run-1"]


# --- Cenário 3: não marca cedo demais ------------------------------------


def test_not_marked_complete_while_a_discovered_spec_is_still_untouched(tmp_path):
    """Two specs discovered; only one is driven to VALID (filtered pass) —
    the run must NOT be marked complete just because the filtered subset
    finished, since the other discovered spec is still not VALID."""
    conn = _conn()
    save_collection_run(conn, CollectionRun(run_id="run-1"))
    blob_store = FilesystemRawBlobStore(tmp_path, conn)
    capture_repo = SqliteRawCaptureRepository(conn)

    # discovery-only pass over the two-spec fixture
    t0 = FakeBrowserTransport()
    t0.queue_navigate(_capture(TWO_SPEC_MARKET_INDEX_HTML, MARKET_INDEX_URL))
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

    # drive ONLY 62184 to VALID — 61189 remains untouched.
    t1 = FakeBrowserTransport()
    t1.queue_navigate(_capture(TWO_SPEC_MARKET_INDEX_HTML, MARKET_INDEX_URL))
    t1.queue_navigate(_capture(MANIFEST_HTML, _URL_62184))
    t1.queue_navigate(_capture(GROUP_HTML, "https://x/front-axle-steering/407"))
    run_collection_driver(
        t1,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        market_index_url=MARKET_INDEX_URL,
        filters=OperationalFilters(spec_filter=[key_62184]),
    )

    run = get_collection_run(conn, "run-1")
    assert run is not None
    assert run.completed_at is None
    assert [r.run_id for r in list_incomplete_runs(conn, FIXED_SCOPE)] == ["run-1"]


def test_never_marked_complete_when_nothing_was_ever_discovered(tmp_path):
    """A vacuous 'all specs are VALID' over an empty set must never be
    treated as completion (guards the universal-quantifier-over-empty-set
    pitfall explicitly)."""
    conn = _conn()
    save_collection_run(conn, CollectionRun(run_id="run-1"))

    # A market index fixture that yields zero discovered entries would be
    # unusual; instead we exercise the guard directly at the unit level.
    from amayama_scraper.orchestration.collection_driver import _maybe_mark_run_completed

    _maybe_mark_run_completed(conn, "run-1", lambda: datetime.now(UTC))

    run = get_collection_run(conn, "run-1")
    assert run is not None
    assert run.completed_at is None
