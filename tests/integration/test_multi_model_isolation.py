"""004 — isolamento completo entre modelos Volkswagen no mesmo banco.

Cenários A-F pedidos pelo PO na correção de robustez arquitetural sobre a
generalização multi-modelo (002). Cada cenário é um teste real (não apenas
`limit_specs=0`) sobre um banco compartilhado.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from tests.support import AMAROK_CONTEXT, GOL_CONTEXT
from tests.unit.fakes import (
    FakeBrowserTransport,
    InMemoryRawBlobStore,
    InMemoryRawCaptureRepository,
)

from amayama_scraper.checkpoint.collection_run import CollectionRun
from amayama_scraper.domain.collection_context import CollectionContext, ContextScopeMismatchError
from amayama_scraper.domain.discovery import build_market_index_url
from amayama_scraper.ingestion.capture_input import RawCaptureInput
from amayama_scraper.ingestion.capture_kind import CaptureKind
from amayama_scraper.orchestration.collection_driver import (
    OperationalFilters,
    run_collection_driver,
)
from amayama_scraper.orchestration.pipeline import process_capture
from amayama_scraper.orchestration.run_selection import IncompatibleResumeRunError, select_run
from amayama_scraper.parsing.market_index import parse_market_spec_index
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
from amayama_scraper.persistence.repositories.current_state_repo import get_current_state
from amayama_scraper.persistence.repositories.manifest_repo import get_authoritative
from amayama_scraper.persistence.repositories.snapshot_repo import get_snapshot
from amayama_scraper.persistence.repositories.spec_registry_repo import (
    list_by_scope,
    list_discovered_spec_entries,
)
from amayama_scraper.snapshots.snapshot import SnapshotState
from amayama_scraper.transport.port import BrowserCapture

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

# Amarok: 1 spec entry (permite popular COMPLETAMENTE — descoberta,
# manifest, checkpoint ACCEPTED, snapshot VALID, current_state, run
# concluído — em um único fixture pequeno).
AMAROK_MARKET_INDEX_HTML = (FIXTURES / "market_index" / "open_ended_period.html").read_text(
    encoding="utf-8"
)
# GOL: 2 spec entries, nunca navegadas além do MARKET_INDEX nestes testes —
# propositalmente, para provar que nada além da descoberta é herdado.
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


def _synthetic_market_index_html(
    *, breadcrumb_market: str, model_code: str, catalog_id: str
) -> str:
    """Fixture sintética determinística (mesma estrutura verificada contra
    evidência real em open_ended_period.html) — 004 item 3: usada para
    popular DOIS markets reais no mesmo banco sem navegação real."""
    href = (
        "https://www.amayama.com/en/genuine-catalogs/epc/volkswagen-overall/gol/"
        f"{breadcrumb_market.lower().replace(' ', '-')}/{model_code.lower()}-{catalog_id}"
    )
    return f"""<!DOCTYPE html>
<html><body>
  <ul class="epcBreadcrumbs">
    <li><div class="breadcrumbs__last-item" dir="auto">{breadcrumb_market}</div></li>
  </ul>
  <div class="epcVariations">
    <table>
      <tbody>
        <tr class="epcVariations__header"><th>Model</th><th>Prod period</th><th>Grade</th></tr>
        <tr class="epcVariations__row">
          <td><a href="{href}">{model_code}</a></td>
          <td>2024.01 - ...</td>
          <td><span class="info-hint-new" data-content="Trendline"
              title="Trendline">Trendline</span></td>
        </tr>
      </tbody>
    </table>
  </div>
</body></html>"""


def _populate_market_fully(
    conn, blob_store, capture_repo, *, context, market_index_html: str, run_id: str
) -> None:
    """Generaliza `_populate_amarok_fully` para qualquer (manufacturer,
    vehicle_model, market): roda o driver real até a única spec da fixture
    alcançar VALID e o run ser concluído — usado pelo Cenário C para
    popular DOIS markets de verdade no mesmo banco (004 item 3)."""
    url = build_market_index_url(context)
    result = parse_market_spec_index(market_index_html, source_capture_id="cap-x")
    assert result.entries, "market_index_html must contain at least one spec entry"
    spec_url = result.entries[0].source_url

    save_collection_run(conn, CollectionRun(run_id=run_id, scope=context.scope()))
    transport = FakeBrowserTransport()
    transport.queue_navigate(_capture(market_index_html, url))
    transport.queue_navigate(_capture(MANIFEST_HTML, spec_url))
    transport.queue_navigate(_capture(GROUP_HTML, "https://x/front-axle-steering/407"))

    run_collection_driver(
        transport,
        conn,
        blob_store,
        capture_repo,
        run_id=run_id,
        context=context,
        filters=OperationalFilters(),
        on_event=lambda *a, **kw: None,
    )

    run = get_collection_run(conn, run_id)
    assert run is not None and run.completed_at is not None, f"setup: {run_id} must complete"


def _amarok_spec_url() -> str:
    result = parse_market_spec_index(AMAROK_MARKET_INDEX_HTML, source_capture_id="cap-x")
    assert result.entries, "AMAROK_MARKET_INDEX_HTML must contain at least one spec entry"
    return result.entries[0].source_url


def _conn(tmp_path: Path):
    conn = connect(str(tmp_path / "db.sqlite3"))
    run_migrations(conn)
    return conn


def _populate_amarok_fully(conn, blob_store, capture_repo, tmp_path: Path) -> None:
    """Roda o driver real (MARKET_INDEX -> SPEC_NAVIGATION -> GROUP_DETAIL)
    até a única spec da fixture alcançar VALID e o run ser concluído —
    "Amarok completamente populada" para o Cenário A."""
    amarok_url = build_market_index_url(AMAROK_CONTEXT)
    spec_url = _amarok_spec_url()

    save_collection_run(conn, CollectionRun(run_id="run-amarok", scope=AMAROK_CONTEXT.scope()))
    transport = FakeBrowserTransport()
    transport.queue_navigate(_capture(AMAROK_MARKET_INDEX_HTML, amarok_url))
    transport.queue_navigate(_capture(MANIFEST_HTML, spec_url))
    transport.queue_navigate(_capture(GROUP_HTML, "https://x/front-axle-steering/407"))

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


# --- Cenário A -------------------------------------------------------------


def test_scenario_a_gol_inherits_nothing_from_a_fully_populated_amarok(tmp_path: Path):
    conn = _conn(tmp_path)
    # SQLite-backed repos reais (não os fakes em memória): checkpoint_entry
    # tem FK para raw_capture — necessário para o fluxo completo até
    # GROUP_DETAIL ACCEPTED/finalize_spec_entry() usado para popular a
    # Amarok de verdade neste cenário.
    blob_store = FilesystemRawBlobStore(tmp_path / "blobs", conn)
    capture_repo = SqliteRawCaptureRepository(conn)

    _populate_amarok_fully(conn, blob_store, capture_repo, tmp_path)
    amarok_specs = list_by_scope(
        conn, manufacturer="VOLKSWAGEN", vehicle_model="AMAROK", market="AMA-BR"
    )
    assert len(amarok_specs) == 1
    assert get_current_state(conn, amarok_specs[0].stable_key()) is not None  # setup sanity

    # Agora inicia GOL — MARKET_INDEX apenas.
    gol_url = build_market_index_url(GOL_CONTEXT)
    save_collection_run(conn, CollectionRun(run_id="run-gol", scope=GOL_CONTEXT.scope()))
    gol_transport = FakeBrowserTransport()
    gol_transport.queue_navigate(_capture(GOL_MARKET_INDEX_HTML, gol_url))
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

    gol_specs = list_by_scope(conn, manufacturer="VOLKSWAGEN", vehicle_model="GOL", market="AMA-BR")
    assert len(gol_specs) == 2  # descoberta aconteceu — mas nada além disso

    for spec in gol_specs:
        key = spec.stable_key()
        # nenhum current_state (nunca alcançou VALID)
        assert get_current_state(conn, key) is None
        # nenhum manifest autoritativo para o run de GOL
        assert get_authoritative(conn, key, "run-gol") is None
        # nenhum checkpoint (nenhum GROUP_DETAIL foi navegado)
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM checkpoint_entry WHERE spec_key = ?", (key,)
        ).fetchone()
        assert row["c"] == 0
        # nenhum snapshot
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM spec_snapshot WHERE spec_identity_ref = ?", (key,)
        ).fetchone()
        assert row["c"] == 0

    # o run de GOL permanece incompleto mesmo com Amarok 100% VALID no mesmo banco
    gol_run = get_collection_run(conn, "run-gol")
    assert gol_run is not None
    assert gol_run.completed_at is None

    # a spec da Amarok continua intocada
    amarok_specs_after = list_by_scope(
        conn, manufacturer="VOLKSWAGEN", vehicle_model="AMAROK", market="AMA-BR"
    )
    assert len(amarok_specs_after) == 1


# --- Cenário B ---------------------------------------------------------


def test_scenario_b_same_model_code_and_catalog_id_different_vehicle_model_no_collision(
    tmp_path: Path,
):
    conn = _conn(tmp_path)
    blob_store, capture_repo = InMemoryRawBlobStore(), InMemoryRawCaptureRepository()

    shared_html = GOL_MARKET_INDEX_HTML  # reaproveita as 2 entries reais como "mesma spec"
    amarok_context = AMAROK_CONTEXT
    another_context = GOL_CONTEXT

    for context, run_id, url in (
        (amarok_context, "run-a", build_market_index_url(amarok_context)),
        (another_context, "run-b", build_market_index_url(another_context)),
    ):
        save_collection_run(conn, CollectionRun(run_id=run_id, scope=context.scope()))
        process_capture(
            conn,
            blob_store,
            capture_repo,
            run_id,
            RawCaptureInput(
                capture_kind=CaptureKind.MARKET_INDEX,
                source_url=url,
                collected_at=datetime.now(UTC),
                raw_content=shared_html.encode("utf-8"),
                run_id=run_id,
            ),
            context=context,
        )

    amarok_specs = list_by_scope(
        conn, manufacturer="VOLKSWAGEN", vehicle_model="AMAROK", market="AMA-BR"
    )
    gol_specs = list_by_scope(conn, manufacturer="VOLKSWAGEN", vehicle_model="GOL", market="AMA-BR")
    assert len(amarok_specs) == 2
    assert len(gol_specs) == 2

    amarok_pairs = {(s.model_code, s.amayama_catalog_id) for s in amarok_specs}
    gol_pairs = {(s.model_code, s.amayama_catalog_id) for s in gol_specs}
    assert amarok_pairs == gol_pairs  # mesmíssimo model_code/catalog_id nos dois lados

    amarok_keys = {s.stable_key() for s in amarok_specs}
    gol_keys = {s.stable_key() for s in gol_specs}
    assert amarok_keys.isdisjoint(gol_keys)  # nenhuma colisão de identidade

    # nenhuma colisão de estado: current_state é None para ambos os lados
    # (nenhum navegou além do MARKET_INDEX) e independente por stable_key
    for key in amarok_keys | gol_keys:
        assert get_current_state(conn, key) is None


# --- Cenário C ---------------------------------------------------------


def test_scenario_c_same_vehicle_model_different_market_isolated(tmp_path: Path) -> None:
    """004 item 3: dados REAIS (via o driver completo, não SQL cru) para
    DOIS markets do MESMO vehicle_model no MESMO banco — GOL/AMA-BR e
    GOL/AMA-US — cada um com spec_registry, discovered_spec_entry,
    manifest, checkpoint, snapshot e current_state próprios."""
    conn = _conn(tmp_path)
    blob_store = FilesystemRawBlobStore(tmp_path / "blobs", conn)
    capture_repo = SqliteRawCaptureRepository(conn)

    market_br = CollectionContext(manufacturer="VOLKSWAGEN", vehicle_model="GOL", market="AMA-BR")
    market_us = CollectionContext(manufacturer="VOLKSWAGEN", vehicle_model="GOL", market="AMA-US")
    assert market_br.scope() != market_us.scope()

    html_br = _synthetic_market_index_html(
        breadcrumb_market="AMA BR", model_code="GOLBR1", catalog_id="10001"
    )
    html_us = _synthetic_market_index_html(
        breadcrumb_market="AMA US", model_code="GOLUS1", catalog_id="20002"
    )

    _populate_market_fully(
        conn,
        blob_store,
        capture_repo,
        context=market_br,
        market_index_html=html_br,
        run_id="run-br",
    )
    _populate_market_fully(
        conn,
        blob_store,
        capture_repo,
        context=market_us,
        market_index_html=html_us,
        run_id="run-us",
    )

    br_specs = list_by_scope(conn, manufacturer="VOLKSWAGEN", vehicle_model="GOL", market="AMA-BR")
    us_specs = list_by_scope(conn, manufacturer="VOLKSWAGEN", vehicle_model="GOL", market="AMA-US")
    assert len(br_specs) == 1
    assert len(us_specs) == 1
    br_key, us_key = br_specs[0].stable_key(), us_specs[0].stable_key()

    # stable_keys diferentes
    assert br_key != us_key

    # discovered_spec_entry separados
    assert len(list_discovered_spec_entries(conn, br_key)) == 1
    assert len(list_discovered_spec_entries(conn, us_key)) == 1

    # manifests separados (cada um autoritativo só no próprio run)
    assert get_authoritative(conn, br_key, "run-br") is not None
    assert get_authoritative(conn, us_key, "run-us") is not None
    assert get_authoritative(conn, br_key, "run-us") is None
    assert get_authoritative(conn, us_key, "run-br") is None

    # checkpoints separados (por run_id + spec_key)
    br_checkpoints = conn.execute(
        "SELECT COUNT(*) AS c FROM checkpoint_entry WHERE run_id = 'run-br' AND spec_key = ?",
        (br_key,),
    ).fetchone()["c"]
    us_checkpoints = conn.execute(
        "SELECT COUNT(*) AS c FROM checkpoint_entry WHERE run_id = 'run-us' AND spec_key = ?",
        (us_key,),
    ).fetchone()["c"]
    assert br_checkpoints == 1
    assert us_checkpoints == 1
    cross_checkpoints = conn.execute(
        "SELECT COUNT(*) AS c FROM checkpoint_entry WHERE run_id = 'run-br' AND spec_key = ?",
        (us_key,),
    ).fetchone()["c"]
    assert cross_checkpoints == 0

    # snapshots separados
    br_current = get_current_state(conn, br_key)
    us_current = get_current_state(conn, us_key)
    assert br_current is not None
    assert us_current is not None
    assert br_current.latest_snapshot_id != us_current.latest_snapshot_id
    br_snapshot = get_snapshot(conn, br_current.latest_snapshot_id)
    us_snapshot = get_snapshot(conn, us_current.latest_snapshot_id)
    assert br_snapshot is not None and us_snapshot is not None
    assert br_snapshot.state == SnapshotState.VALID
    assert us_snapshot.state == SnapshotState.VALID

    # VALID independente + conclusão de um run não depende do outro:
    # ambos já concluíram (checado dentro de _populate_market_fully), e
    # nenhum market aparece sob o scope do outro.
    assert list_by_scope(conn, manufacturer="VOLKSWAGEN", vehicle_model="GOL", market="AMA-US") == (
        us_specs
    )
    assert list_incomplete_runs(conn, market_br.scope()) == []
    assert list_incomplete_runs(conn, market_us.scope()) == []


# --- Cenário D ---------------------------------------------------------


def test_scenario_d_resume_across_models_is_rejected(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    save_collection_run(
        conn, CollectionRun(run_id="run-amarok-old", scope=AMAROK_CONTEXT.scope())
    )

    with pytest.raises(IncompatibleResumeRunError):
        select_run(
            resume_run_id="run-amarok-old",
            new_run=False,
            scope=GOL_CONTEXT.scope(),
            now=datetime.now(UTC),
            run_id_factory=lambda: "unused",
            get_collection_run=lambda rid: get_collection_run(conn, rid),
            list_incomplete_runs=lambda scope: list_incomplete_runs(conn, scope),
            save_collection_run=lambda run: save_collection_run(conn, run),
        )


# --- Cenário E ---------------------------------------------------------


def test_scenario_e_wrong_context_for_an_existing_run_fails_before_any_navigation(
    tmp_path: Path,
) -> None:
    conn = _conn(tmp_path)
    blob_store = FilesystemRawBlobStore(tmp_path / "blobs", conn)
    capture_repo = SqliteRawCaptureRepository(conn)
    save_collection_run(conn, CollectionRun(run_id="run-amarok", scope=AMAROK_CONTEXT.scope()))

    transport = FakeBrowserTransport()  # nenhuma resposta enfileirada de propósito

    with pytest.raises(ContextScopeMismatchError):
        run_collection_driver(
            transport,
            conn,
            blob_store,
            capture_repo,
            run_id="run-amarok",
            context=GOL_CONTEXT,
            filters=OperationalFilters(),
            on_event=lambda *a, **kw: None,
        )

    # se navigate() tivesse sido chamado, o fake teria levantado
    # AssertionError (fila vazia) em vez de ContextScopeMismatchError —
    # a lista abaixo prova que nenhuma navegação sequer foi tentada.
    assert transport.navigate_calls == []
    assert conn.execute("SELECT COUNT(*) AS c FROM raw_capture").fetchone()["c"] == 0
    gol_specs = list_by_scope(conn, manufacturer="VOLKSWAGEN", vehicle_model="GOL", market="AMA-BR")
    assert gol_specs == []


# --- Cenário F ---------------------------------------------------------


def test_scenario_f_market_index_response_for_a_different_market_aborts_the_run(
    tmp_path: Path,
) -> None:
    conn = _conn(tmp_path)
    blob_store = FilesystemRawBlobStore(tmp_path / "blobs", conn)
    capture_repo = SqliteRawCaptureRepository(conn)

    other_market_context = CollectionContext(
        manufacturer="VOLKSWAGEN", vehicle_model="AMAROK", market="AMA-US"
    )
    save_collection_run(
        conn, CollectionRun(run_id="run-1", scope=other_market_context.scope())
    )

    url = build_market_index_url(other_market_context)
    transport = FakeBrowserTransport()
    # a página real devolvida tem breadcrumb "AMA-BR" — diverge do
    # context.market ("AMA-US") deste run.
    transport.queue_navigate(_capture(AMAROK_MARKET_INDEX_HTML, url))

    events: list[tuple[str, dict[str, object]]] = []
    run_collection_driver(
        transport,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        context=other_market_context,
        filters=OperationalFilters(),
        on_event=lambda event, **kw: events.append((event, kw)),
    )

    assert any(event == "RUN_ABORTED" for event, _ in events)
    assert conn.execute("SELECT COUNT(*) AS c FROM spec_registry").fetchone()["c"] == 0
    # a página em si foi capturada (Constitution §4) — só não virou spec
    assert conn.execute("SELECT COUNT(*) AS c FROM raw_capture").fetchone()["c"] == 1
