"""Evolução multi-modelo do scraper (002 + 004): o mesmo pipeline validado da
Amarok/AMA-BR deve coletar outros modelos Volkswagen sem misturar specs,
checkpoints ou runs entre modelos, e sem nenhum model_code/catalog_id
específico hardcoded na atribuição de identidade (`orchestration/pipeline.py`).

Cenários mais profundos de isolamento (A-F, 004) vivem em
tests/integration/test_multi_model_isolation.py — este arquivo cobre a
prova original (002) de ausência de hardcode e coexistência básica, agora
sobre a API de `CollectionContext` (004).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from tests.support import AMAROK_CONTEXT, GOL_CONTEXT
from tests.unit.fakes import (
    FakeBrowserTransport,
    InMemoryRawBlobStore,
    InMemoryRawCaptureRepository,
)

from amayama_scraper.checkpoint.collection_run import CollectionRun
from amayama_scraper.domain.discovery import build_market_index_url
from amayama_scraper.ingestion.capture_input import RawCaptureInput
from amayama_scraper.ingestion.capture_kind import CaptureKind
from amayama_scraper.orchestration.collection_driver import (
    OperationalFilters,
    run_collection_driver,
)
from amayama_scraper.orchestration.pipeline import process_capture
from amayama_scraper.persistence.db import connect
from amayama_scraper.persistence.migrations.runner import run_migrations
from amayama_scraper.persistence.repositories.checkpoint_repo import save_collection_run
from amayama_scraper.persistence.repositories.spec_registry_repo import list_by_scope
from amayama_scraper.transport.port import BrowserCapture

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
MARKET_INDEX_HTML = (FIXTURES / "market_index" / "same_model_code_diff_catalog.html").read_text(
    encoding="utf-8"
)


def _capture(html: str, url: str) -> BrowserCapture:
    return BrowserCapture(page_source=html, effective_url=url, captured_at=datetime.now(UTC))


def test_market_index_capture_assigns_manufacturer_and_vehicle_model_from_parameters(
    tmp_path: Path,
) -> None:
    """Prova de ausência de hardcode: process_capture(), passando um
    CollectionContext de GOL (distinto do default Amarok), registra
    SpecIdentity com esses valores — nunca força VOLKSWAGEN/AMAROK."""
    conn = connect(str(tmp_path / "db.sqlite3"))
    run_migrations(conn)
    save_collection_run(conn, CollectionRun(run_id="run-1", scope=GOL_CONTEXT.scope()))
    blob_store, capture_repo = InMemoryRawBlobStore(), InMemoryRawCaptureRepository()

    process_capture(
        conn,
        blob_store,
        capture_repo,
        "run-1",
        RawCaptureInput(
            capture_kind=CaptureKind.MARKET_INDEX,
            source_url=(
                "https://www.amayama.com/en/genuine-catalogs/epc/volkswagen-overall/gol/ama-br"
            ),
            collected_at=datetime.now(UTC),
            raw_content=MARKET_INDEX_HTML.encode("utf-8"),
            run_id="run-1",
        ),
        context=GOL_CONTEXT,
    )

    discovered = list_by_scope(
        conn, manufacturer="VOLKSWAGEN", vehicle_model="GOL", market="AMA-BR"
    )
    assert len(discovered) == 2
    assert {identity.vehicle_model for identity in discovered} == {"GOL"}

    # nada foi registrado sob o scope Amarok por engano
    amarok_leak = list_by_scope(
        conn, manufacturer="VOLKSWAGEN", vehicle_model="AMAROK", market="AMA-BR"
    )
    assert amarok_leak == []


def test_specs_of_different_models_coexist_without_interference(tmp_path: Path) -> None:
    conn = connect(str(tmp_path / "db.sqlite3"))
    run_migrations(conn)

    assert AMAROK_CONTEXT.scope() != GOL_CONTEXT.scope()

    save_collection_run(conn, CollectionRun(run_id="run-amarok", scope=AMAROK_CONTEXT.scope()))
    save_collection_run(conn, CollectionRun(run_id="run-gol", scope=GOL_CONTEXT.scope()))

    blob_store, capture_repo = InMemoryRawBlobStore(), InMemoryRawCaptureRepository()

    amarok_url = build_market_index_url(AMAROK_CONTEXT)
    amarok_transport = FakeBrowserTransport()
    amarok_transport.queue_navigate(_capture(MARKET_INDEX_HTML, amarok_url))
    run_collection_driver(
        amarok_transport,
        conn,
        blob_store,
        capture_repo,
        run_id="run-amarok",
        context=AMAROK_CONTEXT,
        filters=OperationalFilters(limit_specs=0),
        on_event=lambda *a, **kw: None,
    )

    gol_url = build_market_index_url(GOL_CONTEXT)
    gol_transport = FakeBrowserTransport()
    gol_transport.queue_navigate(_capture(MARKET_INDEX_HTML, gol_url))
    run_collection_driver(
        gol_transport,
        conn,
        blob_store,
        capture_repo,
        run_id="run-gol",
        context=GOL_CONTEXT,
        filters=OperationalFilters(limit_specs=0),
        on_event=lambda *a, **kw: None,
    )

    amarok_specs = list_by_scope(
        conn, manufacturer="VOLKSWAGEN", vehicle_model="AMAROK", market="AMA-BR"
    )
    gol_specs = list_by_scope(conn, manufacturer="VOLKSWAGEN", vehicle_model="GOL", market="AMA-BR")

    assert len(amarok_specs) == 2
    assert len(gol_specs) == 2
    assert {s.vehicle_model for s in amarok_specs} == {"AMAROK"}
    assert {s.vehicle_model for s in gol_specs} == {"GOL"}

    amarok_keys = {s.stable_key() for s in amarok_specs}
    gol_keys = {s.stable_key() for s in gol_specs}
    assert amarok_keys.isdisjoint(gol_keys)

    # a Amarok navegou só na sua própria URL — nunca na do outro modelo
    assert amarok_transport.navigate_calls == [amarok_url]
    assert gol_transport.navigate_calls == [gol_url]
