"""005 hardening (post-review, 2ª rodada) — BLOCKER: terminalidade real via
disposição explícita (`spec_pool_disposition`), nunca backoff temporal.

Diferencia obrigatoriamente:

- **Retry manual** (`MANUAL_RETRY_REQUIRED`): unidades cujo retry normal não
  é permitido (`GROUP_REJECTED_AWAITING_MANUAL_RETRY`) — inelegíveis mesmo
  depois de tempo/nova sessão; só `--retry-rejected` reabre.
- **Falha transitória sem progresso** (`DEFERRED_THIS_SESSION`): ex.
  challenge timeout — inelegível apenas na MESMA invocação de `run_pool()`
  (`pool_session_id`); uma nova invocação (`--resume`) pode tentar de novo.

Usa `next_claimable_spec()`/`run_worker_loop()`/`process_one_spec()`
diretamente, com clocks/fakes controlados — sem sleeps longos."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from tests.support import AMAROK_CONTEXT
from tests.unit.fakes import FakeBrowserTransport

from amayama_scraper.checkpoint.collection_run import CollectionRun
from amayama_scraper.domain.identity import SpecIdentity
from amayama_scraper.orchestration.collection_driver import OperationalFilters
from amayama_scraper.orchestration.worker_pool import (
    WorkerPoolConfig,
    next_claimable_spec,
    run_worker_loop,
)
from amayama_scraper.persistence.adapters.filesystem_raw_blob_store import FilesystemRawBlobStore
from amayama_scraper.persistence.adapters.sqlite_raw_capture_repository import (
    SqliteRawCaptureRepository,
)
from amayama_scraper.persistence.db import connect
from amayama_scraper.persistence.migrations.runner import run_migrations
from amayama_scraper.persistence.repositories import spec_pool_disposition_repo
from amayama_scraper.persistence.repositories.checkpoint_repo import save_collection_run
from amayama_scraper.persistence.repositories.current_state_repo import get_current_state
from amayama_scraper.persistence.repositories.spec_registry_repo import save_spec_identity
from amayama_scraper.transport.port import BrowserCapture

MANIFEST_HTML_ONE_GROUP = """
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

INVALID_GROUP_HTML = "<html><body><h1>not epc content</h1></body></html>"

VALID_GROUP_HTML = """
<html><body><div class="epcVariation__details"><div class="epcSchema__schemas">
  <div class="epcSchema__schema" data-id="SCH-1"><table class="entriesTable">
    <tr data-key="A01"><td class="entriesTable__number">1K0407151</td>
    <td class="entriesTable__description">Control arm</td>
    <td class="entriesTable__period">08.2010-12.2015</td>
    <td class="entriesTable__required">1</td></tr>
  </table></div>
</div></div></body></html>
"""


def _load_challenge_html() -> str:
    fixtures = Path(__file__).resolve().parents[1] / "fixtures"
    return (fixtures / "challenge_cloudflare.html").read_text(encoding="utf-8")


def _capture(html: str, url: str) -> BrowserCapture:
    return BrowserCapture(page_source=html, effective_url=url, captured_at=datetime.now(UTC))


def _spec(index: int = 1) -> SpecIdentity:
    return SpecIdentity(
        source=AMAROK_CONTEXT.source,
        manufacturer=AMAROK_CONTEXT.manufacturer,
        vehicle_model=AMAROK_CONTEXT.vehicle_model,
        market=AMAROK_CONTEXT.market,
        model_code=f"MODEL{index}",
        amayama_catalog_id=f"CAT{index}",
        production_period_raw="01.2020-current",
        source_url=f"https://x/spec-{index}",
    )


def _setup(tmp_path: Path, *, spec: SpecIdentity | None = None):
    conn = connect(str(tmp_path / "pool.db"))
    run_migrations(conn)
    save_collection_run(conn, CollectionRun(run_id="run-1", scope=AMAROK_CONTEXT.scope()))
    spec = spec or _spec()
    save_spec_identity(conn, spec)
    blob_store = FilesystemRawBlobStore(tmp_path / "blobs", conn)
    capture_repo = SqliteRawCaptureRepository(conn)
    return conn, spec, blob_store, capture_repo


# --- 1. Challenge timeout: DEFERRED_THIS_SESSION, retomável num --resume ---


def test_challenge_timeout_defers_within_session_but_resume_can_retry(tmp_path: Path) -> None:
    conn, spec, blob_store, capture_repo = _setup(tmp_path)
    key = spec.stable_key()
    challenge_html = _load_challenge_html()
    t0 = datetime(2026, 9, 3, 12, 0, 0, tzinfo=UTC)
    pool_config = WorkerPoolConfig(workers=1, lease_seconds=60.0)
    session_1 = "pool-session-1"

    clock = {"now": t0}

    def now_fn() -> datetime:
        return clock["now"]

    def advancing_sleep(_seconds: float) -> None:
        clock["now"] = clock["now"] + timedelta(seconds=1)

    transport = FakeBrowserTransport()
    transport.queue_navigate(_capture(challenge_html, spec.source_url))
    transport.queue_current_capture(_capture(challenge_html, spec.source_url))

    # A spec é claimada, o challenge nunca resolve (timeout), termina sem
    # progresso — E o pool ATINGE ESTADO TERMINAL sozinho (run_worker_loop
    # retorna sem hang: depois do release, a única spec fica
    # DEFERRED_THIS_SESSION, next_claimable_spec() não encontra mais nada
    # elegível e devolve throttled=False).
    run_worker_loop(
        transport,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        context=AMAROK_CONTEXT,
        worker_id="worker-0",
        filters=OperationalFilters(),
        pool_config=pool_config,
        pool_session_id=session_1,
        poll_interval=0.0,
        challenge_timeout=0.0,  # expira no primeiro poll — determinístico
        sleep=advancing_sleep,
        now=now_fn,
    )

    disposition = spec_pool_disposition_repo.get(conn, run_id="run-1", spec_key=key)
    assert disposition is not None
    assert disposition.state == "DEFERRED_THIS_SESSION"
    assert disposition.pool_session_id == session_1
    assert get_current_state(conn, key) is None  # sem progresso — nunca VALID

    # Nunca reclamada de novo NA MESMA sessão — e isso é justamente o motivo
    # do pool ter atingido terminal (throttled=False) acima.
    still_same_session = next_claimable_spec(
        conn,
        run_id="run-1",
        context=AMAROK_CONTEXT,
        worker_id="worker-1",
        filters=OperationalFilters(),
        pool_config=pool_config,
        pool_session_id=session_1,
        now=clock["now"],
    )
    assert still_same_session.claimed is None
    assert not still_same_session.throttled  # terminal genuíno para esta sessão

    # Uma nova invocação de run_pool() (--resume) gera outro pool_session_id
    # — a falha transitória pode ser tentada de novo, e desta vez resolve.
    session_2 = "pool-session-2"
    resume_transport = FakeBrowserTransport()
    resume_transport.queue_navigate(_capture(MANIFEST_HTML_ONE_GROUP, spec.source_url))
    resume_transport.queue_navigate(_capture(VALID_GROUP_HTML, "https://x/front-axle-steering/407"))
    run_worker_loop(
        resume_transport,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        context=AMAROK_CONTEXT,
        worker_id="worker-0",
        filters=OperationalFilters(),
        pool_config=pool_config,
        pool_session_id=session_2,
        sleep=lambda _s: None,
        now=lambda: clock["now"],
    )
    assert get_current_state(conn, key) is not None  # desta vez alcançou VALID
    assert spec_pool_disposition_repo.get(conn, run_id="run-1", spec_key=key) is None  # limpa


# --- 2. Retry manual: nunca reelegível sem --retry-rejected -----------------


def test_manual_retry_required_blocks_normal_reclaim_until_retry_rejected(tmp_path: Path) -> None:
    conn, spec, blob_store, capture_repo = _setup(tmp_path)
    key = spec.stable_key()
    t0 = datetime(2026, 9, 3, 12, 0, 0, tzinfo=UTC)
    pool_config = WorkerPoolConfig(workers=1, lease_seconds=60.0)

    # Passagem 1 (sessão A): grupo estruturalmente inválido — tentativa
    # REAL de navegação (não um skip), termina REJECTED. Isso por si só
    # ainda não é "retry manual" (a classificação REQUIRES_EXPLICIT_RETRY
    # só existe a partir de uma passagem SEGUINTE que encontra o
    # checkpoint já REJECTED — mesma semântica pré-existente de
    # retry_classification.py, nunca alterada aqui).
    transport_a = FakeBrowserTransport()
    transport_a.queue_navigate(_capture(MANIFEST_HTML_ONE_GROUP, spec.source_url))
    transport_a.queue_navigate(_capture(INVALID_GROUP_HTML, "https://x/front-axle-steering/407"))
    run_worker_loop(
        transport_a,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        context=AMAROK_CONTEXT,
        worker_id="worker-0",
        filters=OperationalFilters(),
        pool_config=pool_config,
        pool_session_id="session-A",
        sleep=lambda _s: None,
        now=lambda: t0,
    )
    assert spec_pool_disposition_repo.get(conn, run_id="run-1", spec_key=key).state == (
        "DEFERRED_THIS_SESSION"
    )

    # Passagem 2 (sessão B — nova invocação): reivindicada de novo; desta
    # vez o grupo JÁ está REJECTED no checkpoint — classify_pending_unit()
    # o marca REQUIRES_EXPLICIT_RETRY, é PULADO sem navegar (fila do fake
    # vazia — uma tentativa de navegação levantaria AssertionError) — a
    # disposição vira MANUAL_RETRY_REQUIRED.
    transport_b = FakeBrowserTransport()  # nenhuma resposta enfileirada de propósito
    run_worker_loop(
        transport_b,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        context=AMAROK_CONTEXT,
        worker_id="worker-0",
        filters=OperationalFilters(),
        pool_config=pool_config,
        pool_session_id="session-B",
        sleep=lambda _s: None,
        now=lambda: t0,
    )
    assert transport_b.navigate_calls == []
    assert spec_pool_disposition_repo.get(conn, run_id="run-1", spec_key=key).state == (
        "MANUAL_RETRY_REQUIRED"
    )

    # Nunca reclamada de novo no mesmo pool (sessão B).
    same_session = next_claimable_spec(
        conn,
        run_id="run-1",
        context=AMAROK_CONTEXT,
        worker_id="worker-1",
        filters=OperationalFilters(),
        pool_config=pool_config,
        pool_session_id="session-B",
        now=t0,
    )
    assert same_session.claimed is None

    # Uma execução NORMAL nova (sessão C, sem --retry-rejected) também não
    # a reclama — MANUAL_RETRY_REQUIRED independe de tempo/sessão.
    new_normal_session = next_claimable_spec(
        conn,
        run_id="run-1",
        context=AMAROK_CONTEXT,
        worker_id="worker-1",
        filters=OperationalFilters(retry_rejected=False),
        pool_config=pool_config,
        pool_session_id="session-C",
        now=t0 + timedelta(days=1),
    )
    assert new_normal_session.claimed is None
    assert not new_normal_session.throttled  # terminal — nada mais elegível

    # --retry-rejected reabre — reivindica e, desta vez, o grupo (ainda
    # inválido no fake) é reatentado de verdade.
    retry_transport = FakeBrowserTransport()
    retry_transport.queue_navigate(_capture(VALID_GROUP_HTML, "https://x/front-axle-steering/407"))
    run_worker_loop(
        retry_transport,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        context=AMAROK_CONTEXT,
        worker_id="worker-0",
        filters=OperationalFilters(retry_rejected=True),
        pool_config=pool_config,
        pool_session_id="session-D",
        sleep=lambda _s: None,
        now=lambda: t0 + timedelta(days=1),
    )
    assert retry_transport.navigate_calls == ["https://x/front-axle-steering/407"]
    assert get_current_state(conn, key) is not None  # progresso real desta vez
    assert spec_pool_disposition_repo.get(conn, run_id="run-1", spec_key=key) is None  # limpa


# --- 3. Múltiplos workers atingem terminal, nenhum fica em loop ------------


def test_multiple_workers_reach_terminal_state_when_only_ineligible_specs_remain(
    tmp_path: Path,
) -> None:
    conn, spec_a, blob_store, capture_repo = _setup(tmp_path, spec=_spec(1))
    spec_b = _spec(2)
    save_spec_identity(conn, spec_b)
    key_a, key_b = spec_a.stable_key(), spec_b.stable_key()

    t0 = datetime(2026, 9, 3, 12, 0, 0, tzinfo=UTC)
    session = "pool-session-shared"
    spec_pool_disposition_repo.set_manual_retry_required(
        conn, run_id="run-1", spec_key=key_a, now=t0
    )
    spec_pool_disposition_repo.set_deferred_this_session(
        conn, run_id="run-1", spec_key=key_b, pool_session_id=session, now=t0
    )

    pool_config = WorkerPoolConfig(workers=2, lease_seconds=60.0)

    # Nenhuma resposta enfileirada em nenhum dos dois — se qualquer worker
    # tentasse reivindicar/navegar, o fake levantaria AssertionError.
    transport_0 = FakeBrowserTransport()
    transport_1 = FakeBrowserTransport()

    run_worker_loop(
        transport_0,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        context=AMAROK_CONTEXT,
        worker_id="worker-0",
        filters=OperationalFilters(),
        pool_config=pool_config,
        pool_session_id=session,
        sleep=lambda _s: None,
        now=lambda: t0,
    )
    run_worker_loop(
        transport_1,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        context=AMAROK_CONTEXT,
        worker_id="worker-1",
        filters=OperationalFilters(),
        pool_config=pool_config,
        pool_session_id=session,
        sleep=lambda _s: None,
        now=lambda: t0,
    )

    # Ambos retornaram (a própria conclusão do teste, sem timeout externo,
    # já prova ausência de loop infinito) sem jamais navegar/reivindicar.
    assert transport_0.navigate_calls == []
    assert transport_1.navigate_calls == []
