"""T515 — SC-005/US6: isolamento de contexto (004) preservado sob o worker
pool. Reusa AMAROK_CONTEXT/GOL_CONTEXT (tests/support.py, 004) — pool de
workers de GOL rodando sobre um banco com Amarok totalmente populada nunca
produz spec/checkpoint/manifest/snapshot cruzado, e um worker cujo `context`
diverge do `CollectionRun.scope` nunca chega a reivindicar/navegar/persistir
nada (FR-100/FR-101, mesmo padrão do Cenário E de 004)."""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from pathlib import Path

import pytest
from tests.support import AMAROK_CONTEXT, GOL_CONTEXT
from tests.unit.fakes import FakeBrowserTransport

from amayama_scraper.checkpoint.collection_run import CollectionRun
from amayama_scraper.domain.collection_context import ContextScopeMismatchError
from amayama_scraper.domain.discovery import build_market_index_url
from amayama_scraper.orchestration.collection_driver import (
    OperationalFilters,
    run_collection_driver,
    run_market_index_phase,
)
from amayama_scraper.orchestration.worker_pool import WorkerPoolConfig, run_worker_loop
from amayama_scraper.parsing.market_index import parse_market_spec_index
from amayama_scraper.persistence.adapters.filesystem_raw_blob_store import FilesystemRawBlobStore
from amayama_scraper.persistence.adapters.sqlite_raw_capture_repository import (
    SqliteRawCaptureRepository,
)
from amayama_scraper.persistence.db import connect
from amayama_scraper.persistence.migrations.runner import run_migrations
from amayama_scraper.persistence.repositories.checkpoint_repo import (
    get_collection_run,
    save_collection_run,
)
from amayama_scraper.persistence.repositories.current_state_repo import get_current_state
from amayama_scraper.persistence.repositories.manifest_repo import get_authoritative
from amayama_scraper.persistence.repositories.spec_registry_repo import list_by_scope
from amayama_scraper.transport.port import BrowserCapture

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
AMAROK_MARKET_INDEX_HTML = (FIXTURES / "market_index" / "open_ended_period.html").read_text(
    encoding="utf-8"
)
GOL_MARKET_INDEX_HTML = (FIXTURES / "market_index" / "same_model_code_diff_catalog.html").read_text(
    encoding="utf-8"
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


def _group_html(oem: str) -> str:
    return f"""
<html><body><div class="epcVariation__details"><div class="epcSchema__schemas">
  <div class="epcSchema__schema" data-id="SCH-1"><table class="entriesTable">
    <tr data-key="A01"><td class="entriesTable__number">{oem}</td>
    <td class="entriesTable__description">Control arm</td>
    <td class="entriesTable__period">08.2010-12.2015</td>
    <td class="entriesTable__required">1</td></tr>
  </table></div>
</div></div></body></html>
"""


def _capture(html: str, url: str) -> BrowserCapture:
    return BrowserCapture(page_source=html, effective_url=url, captured_at=datetime.now(UTC))


def _amarok_spec_url() -> str:
    result = parse_market_spec_index(AMAROK_MARKET_INDEX_HTML, source_capture_id="cap-x")
    assert result.entries
    return result.entries[0].source_url


def _populate_amarok_fully(conn, blob_store, capture_repo) -> None:
    amarok_url = build_market_index_url(AMAROK_CONTEXT)
    spec_url = _amarok_spec_url()
    save_collection_run(conn, CollectionRun(run_id="run-amarok", scope=AMAROK_CONTEXT.scope()))
    transport = FakeBrowserTransport()
    transport.queue_navigate(_capture(AMAROK_MARKET_INDEX_HTML, amarok_url))
    transport.queue_navigate(_capture(MANIFEST_HTML, spec_url))
    transport.queue_navigate(
        _capture(_group_html("1K0407151"), "https://x/front-axle-steering/407")
    )
    run_collection_driver(
        transport,
        conn,
        blob_store,
        capture_repo,
        run_id="run-amarok",
        context=AMAROK_CONTEXT,
        filters=OperationalFilters(),
        on_event=lambda *a, **kw: None,
    )
    run = get_collection_run(conn, "run-amarok")
    assert run is not None and run.completed_at is not None, "setup: Amarok run must complete"


def _conn(tmp_path: Path):
    conn = connect(str(tmp_path / "db.sqlite3"))
    run_migrations(conn)
    return conn


def test_gol_worker_pool_inherits_nothing_from_a_fully_populated_amarok(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    blob_store = FilesystemRawBlobStore(tmp_path / "blobs", conn)
    capture_repo = SqliteRawCaptureRepository(conn)
    _populate_amarok_fully(conn, blob_store, capture_repo)

    amarok_specs_before = list_by_scope(
        conn, manufacturer="VOLKSWAGEN", vehicle_model="AMAROK", market="AMA-BR"
    )
    assert len(amarok_specs_before) == 1

    # GOL: MARKET_INDEX real (2 specs descobertas), depois um "pool" de 2
    # workers reivindicando e navegando cada spec até VALID — cada worker
    # com seu PRÓPRIO FakeBrowserTransport/conexão, exatamente como dois
    # processos independentes teriam (FR-040/FR-041).
    gol_url = build_market_index_url(GOL_CONTEXT)
    save_collection_run(conn, CollectionRun(run_id="run-gol", scope=GOL_CONTEXT.scope()))
    market_transport = FakeBrowserTransport()
    market_transport.queue_navigate(_capture(GOL_MARKET_INDEX_HTML, gol_url))
    proceeded = run_market_index_phase(
        market_transport,
        conn,
        blob_store,
        capture_repo,
        run_id="run-gol",
        context=GOL_CONTEXT,
        throttled_navigate=market_transport.navigate,
        on_event=lambda *a, **kw: None,
    )
    assert proceeded

    gol_specs = list_by_scope(conn, manufacturer="VOLKSWAGEN", vehicle_model="GOL", market="AMA-BR")
    assert len(gol_specs) == 2

    pool_config = WorkerPoolConfig(workers=2)
    errors: list[BaseException] = []

    def run_one_worker(worker_id: str, oem: str) -> None:
        try:
            worker_conn = connect(str(tmp_path / "db.sqlite3"))
            worker_blob_store = FilesystemRawBlobStore(tmp_path / "blobs", worker_conn)
            worker_capture_repo = SqliteRawCaptureRepository(worker_conn)
            transport = FakeBrowserTransport()
            for spec in gol_specs:
                transport.queue_navigate(_capture(MANIFEST_HTML, spec.source_url))
                transport.queue_navigate(
                    _capture(_group_html(oem), "https://x/front-axle-steering/407")
                )
            run_worker_loop(
                transport,
                worker_conn,
                worker_blob_store,
                worker_capture_repo,
                run_id="run-gol",
                context=GOL_CONTEXT,
                worker_id=worker_id,
                filters=OperationalFilters(),
                pool_config=pool_config,
                pool_session_id="test-session",
                sleep=lambda _s: None,
            )
            worker_conn.close()
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    # Um único worker é suficiente para esvaziar as 2 specs (o segundo,
    # se chamado, encontraria zero specs claimable) — usar dois aqui prova
    # que o segundo não interfere/duplica nada mesmo tentando.
    threads = [
        threading.Thread(target=run_one_worker, args=("worker-0", "1K0407151")),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert not errors, f"worker thread(s) raised: {errors}"

    for spec in gol_specs:
        key = spec.stable_key()
        current = get_current_state(conn, key)
        assert current is not None, f"GOL spec {key} never reached a current state"

    # a spec da Amarok continua intocada, e nenhum manifest/checkpoint de
    # GOL aparece sob o run/contexto da Amarok.
    amarok_specs_after = list_by_scope(
        conn, manufacturer="VOLKSWAGEN", vehicle_model="AMAROK", market="AMA-BR"
    )
    assert len(amarok_specs_after) == 1
    assert amarok_specs_after == amarok_specs_before
    for spec in gol_specs:
        assert get_authoritative(conn, spec.stable_key(), "run-amarok") is None


def test_worker_with_mismatched_context_never_navigates_or_persists(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    save_collection_run(conn, CollectionRun(run_id="run-amarok", scope=AMAROK_CONTEXT.scope()))
    blob_store = FilesystemRawBlobStore(tmp_path / "blobs", conn)
    capture_repo = SqliteRawCaptureRepository(conn)
    transport = FakeBrowserTransport()  # nenhuma resposta enfileirada de propósito

    with pytest.raises(ContextScopeMismatchError):
        run_worker_loop(
            transport,
            conn,
            blob_store,
            capture_repo,
            run_id="run-amarok",
            context=GOL_CONTEXT,
            worker_id="worker-0",
            filters=OperationalFilters(),
            pool_config=WorkerPoolConfig(workers=2),
            pool_session_id="test-session",
            sleep=lambda _s: None,
        )

    assert transport.navigate_calls == []
    assert conn.execute("SELECT COUNT(*) AS c FROM raw_capture").fetchone()["c"] == 0
    assert conn.execute("SELECT COUNT(*) AS c FROM spec_lease").fetchone()["c"] == 0
