"""T524 — FR-090/FR-091: retomar um run parcialmente coletado sob o worker
pool reivindica apenas specs/grupos pendentes — zero navegação para
unidades já `ACCEPTED`, spec já `VALID` nunca reivindicada.

Popula o cenário com o driver legado (`run_collection_driver`, --workers 1,
`--limit-groups 1`) para deixar 1 de 2 grupos ACCEPTED e uma manifest já
autoritativa para o run_id — exatamente o estado que uma interrupção real
deixaria. Em seguida, "retoma" via `run_worker_loop()` (mesmo `run_id`,
mesmo `context` — o que `--resume <run_id> --workers N` produziria através
da CLI, run_pool.py:worker_target). O `FakeBrowserTransport` do passo de
retomada só tem o grupo PENDENTE enfileirado — se o driver tentasse
renavegar SPEC_NAVIGATION ou o grupo já ACCEPTED, a fila vazia faria o fake
levantar `AssertionError` (mesma técnica de
tests/integration/test_no_auto_retry_on_validation_rejection.py)."""

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
from amayama_scraper.orchestration.worker_pool import WorkerPoolConfig, run_worker_loop
from amayama_scraper.persistence.adapters.filesystem_raw_blob_store import FilesystemRawBlobStore
from amayama_scraper.persistence.adapters.sqlite_raw_capture_repository import (
    SqliteRawCaptureRepository,
)
from amayama_scraper.persistence.db import connect
from amayama_scraper.persistence.migrations.runner import run_migrations
from amayama_scraper.persistence.repositories.checkpoint_repo import (
    get_collection_run,
    list_accepted,
    save_collection_run,
)
from amayama_scraper.persistence.repositories.current_state_repo import get_current_state
from amayama_scraper.persistence.repositories.snapshot_repo import get_snapshot
from amayama_scraper.snapshots.snapshot import SnapshotState
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

MANIFEST_HTML_TWO_GROUPS = """
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
      <div class="epcVariation__schema" data-id="408">
        <div class="epcVariation__schema-name"><a href="https://x/front-axle-steering/408">408</a></div>
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


def _sole_processed_spec_key(conn, run_id: str) -> str:
    """`same_model_code_diff_catalog.html` descobre 2 specs; `limit_specs=1`
    processa apenas uma — qual delas depende da ordenação por `stable_key`
    (hash), não de um catalog_id fixo. Identifica dinamicamente qual foi
    processada em vez de assumir um catalog_id específico."""
    row = conn.execute(
        "SELECT DISTINCT spec_key FROM checkpoint_entry WHERE run_id = ?", (run_id,)
    ).fetchone()
    assert row is not None, "setup: expected exactly one spec to have been processed"
    return row["spec_key"]


def test_resume_via_worker_pool_never_renavigates_accepted_units(tmp_path: Path) -> None:
    conn = connect(str(tmp_path / "pool.db"))
    run_migrations(conn)
    blob_store = FilesystemRawBlobStore(tmp_path / "blobs", conn)
    capture_repo = SqliteRawCaptureRepository(conn)

    # --- Passo 1: coleta original (--workers 1), interrompida após 1 de 2 grupos.
    save_collection_run(conn, CollectionRun(run_id="run-1", scope=AMAROK_CONTEXT.scope()))
    first_pass_transport = FakeBrowserTransport()
    first_pass_transport.queue_navigate(_capture(MARKET_INDEX_HTML, MARKET_INDEX_URL))
    first_pass_transport.queue_navigate(_capture(MANIFEST_HTML_TWO_GROUPS, _SPEC_URL))
    first_pass_transport.queue_navigate(
        _capture(_group_html("1K0407151"), "https://x/front-axle-steering/407")
    )
    run_collection_driver(
        first_pass_transport,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        context=AMAROK_CONTEXT,
        filters=OperationalFilters(limit_specs=1, limit_groups=1),
        on_event=lambda *a, **kw: None,
    )

    key = _sole_processed_spec_key(conn, "run-1")
    assert get_current_state(conn, key) is None, "setup: spec must NOT be VALID yet (1/2 groups)"
    assert len(list_accepted(conn, "run-1", key)) == 1
    run_after_first_pass = get_collection_run(conn, "run-1")
    assert run_after_first_pass is not None and run_after_first_pass.completed_at is None

    # --- Passo 2: "retomada" via worker pool (mesmo run_id/context) — o
    # fake do worker só tem o grupo PENDENTE enfileirado (nada de
    # MARKET_INDEX/SPEC_NAVIGATION/grupo já ACCEPTED).
    resume_transport = FakeBrowserTransport()
    resume_transport.queue_navigate(
        _capture(_group_html("1K0407152"), "https://x/front-axle-steering/408")
    )

    # `spec_filter=[key]` restringe esta passada à spec já parcialmente
    # coletada (a 2ª spec descoberta pelo MARKET_INDEX, nunca tocada no
    # passo 1, está fora do escopo desta prova — que é especificamente
    # sobre não perder/reprocessar o progresso já ACCEPTED).
    run_worker_loop(
        resume_transport,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        context=AMAROK_CONTEXT,
        worker_id="worker-0",
        filters=OperationalFilters(spec_filter=[key]),
        pool_config=WorkerPoolConfig(workers=2),
        pool_session_id="test-session",
        sleep=lambda _s: None,
    )

    # exatamente 1 navegação — o grupo pendente, nada mais (nenhuma
    # renavegação de MARKET_INDEX/SPEC_NAVIGATION/grupo já ACCEPTED).
    assert resume_transport.navigate_calls == ["https://x/front-axle-steering/408"]

    assert len(list_accepted(conn, "run-1", key)) == 2
    current = get_current_state(conn, key)
    assert current is not None, "spec must reach VALID once the pending group is accepted"
    snapshot = get_snapshot(conn, current.latest_snapshot_id)
    assert snapshot is not None and snapshot.state == SnapshotState.VALID


def test_resume_via_worker_pool_never_claims_an_already_valid_spec(tmp_path: Path) -> None:
    """FR-024/FR-091: uma "retomada" sobre um run já 100% VALID (ambas as
    specs descobertas) não reivindica nem navega nada — `run_worker_loop()`
    encerra imediatamente."""
    conn = connect(str(tmp_path / "pool.db"))
    run_migrations(conn)
    blob_store = FilesystemRawBlobStore(tmp_path / "blobs", conn)
    capture_repo = SqliteRawCaptureRepository(conn)
    save_collection_run(conn, CollectionRun(run_id="run-1", scope=AMAROK_CONTEXT.scope()))

    # Ambas as specs descobertas por MARKET_INDEX_HTML processadas até VALID
    # (nenhum limit_specs desta vez — nada deve sobrar claimable).
    full_transport = FakeBrowserTransport()
    full_transport.queue_navigate(_capture(MARKET_INDEX_HTML, MARKET_INDEX_URL))
    for _ in range(2):
        full_transport.queue_navigate(_capture(MANIFEST_HTML_TWO_GROUPS, _SPEC_URL))
        full_transport.queue_navigate(
            _capture(_group_html("1K0407151"), "https://x/front-axle-steering/407")
        )
        full_transport.queue_navigate(
            _capture(_group_html("1K0407152"), "https://x/front-axle-steering/408")
        )
    run_collection_driver(
        full_transport,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        context=AMAROK_CONTEXT,
        filters=OperationalFilters(),
        on_event=lambda *a, **kw: None,
    )
    processed_keys = {
        row["spec_key"]
        for row in conn.execute(
            "SELECT DISTINCT spec_key FROM checkpoint_entry WHERE run_id = ?", ("run-1",)
        ).fetchall()
    }
    assert len(processed_keys) == 2, "setup: both discovered specs must have been processed"
    for key in processed_keys:
        assert get_current_state(conn, key) is not None, f"setup: spec {key} must be VALID"

    empty_transport = FakeBrowserTransport()  # nenhuma resposta enfileirada de propósito
    run_worker_loop(
        empty_transport,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        context=AMAROK_CONTEXT,
        worker_id="worker-0",
        filters=OperationalFilters(),
        pool_config=WorkerPoolConfig(workers=2),
        pool_session_id="test-session",
        sleep=lambda _s: None,
    )
    assert empty_transport.navigate_calls == []
