"""005 hardening (post-review) — BLOCKER 1: cenário adversarial completo
pedido explicitamente pela revisão:

  worker A claim; lease expira; worker B recupera; QUALQUER persistência
  posterior de A deve falhar/ser descartada; B continua normalmente.

Executado no nível de `run_worker_loop()` real (não apenas `lease_repo`,
já coberto por `tests/unit/test_lease_fencing_token.py`) — prova que o
fencing bloqueia a escrita EFETIVA (`GROUP_DETAIL` -> checkpoint) de um
worker que perdeu a posse, não apenas a leitura do lease."""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

from tests.support import AMAROK_CONTEXT
from tests.unit.fakes import FakeBrowserTransport

from amayama_scraper.checkpoint.collection_run import CollectionRun
from amayama_scraper.domain.identity import SpecIdentity
from amayama_scraper.orchestration.collection_driver import OperationalFilters
from amayama_scraper.orchestration.worker_pool import WorkerPoolConfig, run_worker_loop
from amayama_scraper.persistence.adapters.filesystem_raw_blob_store import FilesystemRawBlobStore
from amayama_scraper.persistence.adapters.sqlite_raw_capture_repository import (
    SqliteRawCaptureRepository,
)
from amayama_scraper.persistence.db import connect
from amayama_scraper.persistence.migrations.runner import run_migrations
from amayama_scraper.persistence.repositories import lease_repo
from amayama_scraper.persistence.repositories.checkpoint_repo import (
    list_accepted,
    save_collection_run,
)
from amayama_scraper.persistence.repositories.current_state_repo import get_current_state
from amayama_scraper.persistence.repositories.spec_registry_repo import save_spec_identity
from amayama_scraper.transport.port import BrowserCapture

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


def _spec() -> SpecIdentity:
    return SpecIdentity(
        source=AMAROK_CONTEXT.source,
        manufacturer=AMAROK_CONTEXT.manufacturer,
        vehicle_model=AMAROK_CONTEXT.vehicle_model,
        market=AMAROK_CONTEXT.market,
        model_code="MODEL1",
        amayama_catalog_id="CAT1",
        production_period_raw="01.2020-current",
        source_url="https://x/spec-1",
    )


def test_worker_a_never_persists_after_worker_b_takeover_and_b_continues_normally(
    tmp_path: Path,
) -> None:
    db_path = str(tmp_path / "pool.db")
    conn = connect(db_path)
    run_migrations(conn)
    save_collection_run(conn, CollectionRun(run_id="run-1", scope=AMAROK_CONTEXT.scope()))
    spec = _spec()
    save_spec_identity(conn, spec)
    key = spec.stable_key()

    blob_store = FilesystemRawBlobStore(tmp_path / "blobs", conn)
    capture_repo = SqliteRawCaptureRepository(conn)

    t0 = datetime(2026, 9, 3, 12, 0, 0, tzinfo=UTC)
    pool_config = WorkerPoolConfig(workers=1, lease_seconds=30.0)

    # Worker A: manifesto + grupo 1 (aceito antes do takeover) + grupo 2
    # (será tentado, mas deve ser REJEITADO pelo fencing).
    transport_a = FakeBrowserTransport()
    transport_a.queue_navigate(_capture(MANIFEST_HTML_TWO_GROUPS, spec.source_url))
    transport_a.queue_navigate(
        _capture(_group_html("1K0407151"), "https://x/front-axle-steering/407")
    )
    transport_a.queue_navigate(
        _capture(_group_html("1K0407152"), "https://x/front-axle-steering/408")
    )

    # Conexão separada simulando o worker B tomando posse "de fora" —
    # exatamente como um segundo PROCESSO faria via sua própria conexão.
    takeover_conn = connect(db_path)
    stop_event = threading.Event()

    def hook(event: str, **fields: object) -> None:
        if event == "GROUP_ACCEPTED" and fields.get("category_slug") == "front-axle-steering":
            # Simula um observador externo o suficiente à frente no tempo
            # para que o lease de A (renovado por último em t0) já esteja
            # expirado — B recupera legitimamente (mesmo caminho de
            # recovery já provado em test_worker_pool_lease_recovery.py).
            lease_repo.try_claim(
                takeover_conn,
                run_id="run-1",
                spec_key=key,
                owner="worker-B",
                now=t0 + timedelta(seconds=1000),
                lease_seconds=30.0,
            )
        if event == "LEASE_LOST":
            stop_event.set()

    run_worker_loop(
        transport_a,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        context=AMAROK_CONTEXT,
        worker_id="worker-A",
        filters=OperationalFilters(),
        pool_config=pool_config,
        pool_session_id="test-session",
        sleep=lambda _s: None,
        now=lambda: t0,
        on_event=hook,
        stop_event=stop_event,
    )

    # Grupo 1 foi aceito por A ANTES do takeover — progresso real preservado.
    accepted = list_accepted(conn, "run-1", key)
    assert len(accepted) == 1
    assert accepted[0].category_slug == "front-axle-steering" and accepted[0].group_id == "407"

    # A posse agora é de B — A nunca conseguiu persistir o grupo 2.
    assert lease_repo.get_lease_owner(conn, run_id="run-1", spec_key=key) == "worker-B"
    assert get_current_state(conn, key) is None  # spec ainda não VALID (grupo 2 pendente)

    # Worker B continua normalmente — reivindica (recovery real, clock
    # avançado além do lease que B mesmo acabou de fixar) e termina o grupo
    # pendente até VALID.
    transport_b = FakeBrowserTransport()
    transport_b.queue_navigate(
        _capture(_group_html("1K0407152"), "https://x/front-axle-steering/408")
    )
    run_worker_loop(
        transport_b,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        context=AMAROK_CONTEXT,
        worker_id="worker-B",
        filters=OperationalFilters(),
        pool_config=pool_config,
        pool_session_id="test-session",
        sleep=lambda _s: None,
        now=lambda: t0 + timedelta(seconds=1031),
    )

    accepted_after = list_accepted(conn, "run-1", key)
    assert len(accepted_after) == 2
    assert get_current_state(conn, key) is not None  # spec alcançou VALID via B
