"""T074/T075 — laço de nível A (MARKET_INDEX): FakeBrowserTransport ->
process_capture() real -> list_all_spec_identities() reflete exatamente a
fixture usada (FR-006, FR-009, US1 cenário 1). Nenhuma lista de spec
entries hardcoded em src/."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from tests.support import AMAROK_CONTEXT
from tests.unit.fakes import (
    FakeBrowserTransport,
    InMemoryRawBlobStore,
    InMemoryRawCaptureRepository,
)

from amayama_scraper.checkpoint.collection_run import CollectionRun
from amayama_scraper.orchestration.collection_driver import (
    OperationalFilters,
    run_collection_driver,
)
from amayama_scraper.persistence.db import connect
from amayama_scraper.persistence.migrations.runner import run_migrations
from amayama_scraper.persistence.repositories.checkpoint_repo import save_collection_run
from amayama_scraper.persistence.repositories.spec_registry_repo import list_all_spec_identities
from amayama_scraper.transport.port import BrowserCapture

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
MARKET_INDEX_HTML = (FIXTURES / "market_index" / "same_model_code_diff_catalog.html").read_text(
    encoding="utf-8"
)
MARKET_INDEX_URL = (
    "https://www.amayama.com/en/genuine-catalogs/epc/volkswagen-overall/amarok/ama-br"
)


def _conn():
    conn = connect(":memory:")
    run_migrations(conn)
    save_collection_run(conn, CollectionRun(run_id="run-1"))
    return conn


def test_market_index_discovery_reflects_fixture_with_no_hardcoded_specs():
    conn = _conn()
    blob_store, capture_repo = InMemoryRawBlobStore(), InMemoryRawCaptureRepository()
    transport = FakeBrowserTransport()
    transport.queue_navigate(
        BrowserCapture(
            page_source=MARKET_INDEX_HTML,
            effective_url=MARKET_INDEX_URL,
            captured_at=datetime.now(UTC),
        )
    )

    run_collection_driver(
        transport,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        context=AMAROK_CONTEXT,
        filters=OperationalFilters(limit_specs=0),
        on_event=lambda *a, **kw: None,
    )

    discovered = list_all_spec_identities(conn)
    catalog_ids = {identity.amayama_catalog_id for identity in discovered}
    assert catalog_ids == {"62184", "61189"}
    assert transport.navigate_calls == [MARKET_INDEX_URL]  # limit_specs=0 -> no further navigation
