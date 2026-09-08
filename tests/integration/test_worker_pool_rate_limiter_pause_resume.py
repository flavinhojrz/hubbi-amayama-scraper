"""005 hardening (post-review) — HIGH 5: um worker sem slot de concorrência
efetiva ("throttled") permanece VIVO e tenta de novo — nunca encerra só
porque momentaneamente não há slot. Cenário pedido explicitamente pela
revisão: começa com 2; challenge reduz para 1; o segundo worker fica
ocioso (retry, não exit); estabilidade recupera para 2; o segundo worker
volta a reivindicar/trabalhar."""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

from tests.support import AMAROK_CONTEXT
from tests.unit.fakes import FakeBrowserTransport

from amayama_scraper.checkpoint.collection_run import CollectionRun
from amayama_scraper.domain.identity import SpecIdentity
from amayama_scraper.orchestration.collection_driver import OperationalFilters
from amayama_scraper.orchestration.rate_limiter import RateLimiterState
from amayama_scraper.orchestration.worker_pool import WorkerPoolConfig, run_worker_loop
from amayama_scraper.persistence.adapters.filesystem_raw_blob_store import FilesystemRawBlobStore
from amayama_scraper.persistence.adapters.sqlite_raw_capture_repository import (
    SqliteRawCaptureRepository,
)
from amayama_scraper.persistence.db import connect
from amayama_scraper.persistence.migrations.runner import run_migrations
from amayama_scraper.persistence.repositories import lease_repo, rate_limiter_repo
from amayama_scraper.persistence.repositories.checkpoint_repo import save_collection_run
from amayama_scraper.persistence.repositories.current_state_repo import get_current_state
from amayama_scraper.persistence.repositories.spec_registry_repo import save_spec_identity
from amayama_scraper.transport.port import BrowserCapture

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


def _spec(index: int) -> SpecIdentity:
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


def test_throttled_worker_stays_alive_and_resumes_once_concurrency_recovers(
    tmp_path: Path,
) -> None:
    db_path = str(tmp_path / "pool.db")
    conn = connect(db_path)
    run_migrations(conn)
    save_collection_run(conn, CollectionRun(run_id="run-1", scope=AMAROK_CONTEXT.scope()))
    spec_a, spec_b = _spec(0), _spec(1)
    save_spec_identity(conn, spec_a)
    save_spec_identity(conn, spec_b)
    key_a, key_b = spec_a.stable_key(), spec_b.stable_key()

    blob_store = FilesystemRawBlobStore(tmp_path / "blobs", conn)
    capture_repo = SqliteRawCaptureRepository(conn)

    t0 = datetime(2026, 9, 3, 12, 0, 0, tzinfo=UTC)
    pool_config = WorkerPoolConfig(
        workers=2, lease_seconds=120.0, stability_seconds=10.0, metrics_interval_seconds=5.0
    )

    # Simula "começa com 2; challenge reduz para 1": estado do rate limiter
    # já degradado, e spec-A com lease ativo (worker-A "trabalhando").
    rate_limiter_repo.write_state(
        conn,
        run_id="run-1",
        state=RateLimiterState(effective_concurrency=1, stable_since=t0),
        now=t0,
    )
    lease_repo.try_claim(
        conn, run_id="run-1", spec_key=key_a, owner="worker-A", now=t0, lease_seconds=120.0
    )

    # Worker-B: sem slot no início (active=1 >= effective_concurrency=1) —
    # deve permanecer vivo, tentando de novo, até a recuperação gradual
    # (FR-064) devolver o segundo slot.
    clock = {"now": t0}
    throttled_events: list[str] = []
    # spec-A permanece leased (worker-A) por todo o teste — sem isto, o
    # próprio worker-B eventualmente veria o lease manual de spec-A expirar
    # (clock avançando via `sleep`) e tentaria reivindicá-la também, o que
    # não é o que este teste quer provar (apenas que B espera e retoma).
    # `stop_event` corta o laço assim que spec-B termina, antes disso.
    stop_event = threading.Event()

    def now_fn() -> datetime:
        return clock["now"]

    def advancing_sleep(_seconds: float) -> None:
        clock["now"] = clock["now"] + timedelta(seconds=3)

    def on_event(event: str, **fields: object) -> None:
        if event == "WORKER_THROTTLED_WAITING_FOR_SLOT":
            throttled_events.append(event)
        elif event == "SPEC_PASS_COMPLETE":
            stop_event.set()

    transport_b = FakeBrowserTransport()
    transport_b.queue_navigate(_capture(MANIFEST_HTML, spec_b.source_url))
    transport_b.queue_navigate(_capture(GROUP_HTML, "https://x/front-axle-steering/407"))

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
        poll_interval=1.0,
        sleep=advancing_sleep,
        now=now_fn,
        on_event=on_event,
        stop_event=stop_event,
    )

    # O worker realmente esperou (múltiplas tentativas throttled) em vez de
    # encerrar na primeira checagem sem slot — prova de que ficou vivo.
    assert len(throttled_events) >= 1

    # E, uma vez recuperado o slot, processou spec-B normalmente até VALID —
    # nunca precisou ser "acordado" por um novo processo/CLI separado.
    assert get_current_state(conn, key_b) is not None

    # spec-A nunca foi tocada por worker-B (permanece sob o lease de worker-A).
    assert lease_repo.get_lease_owner(conn, run_id="run-1", spec_key=key_a) == "worker-A"
    assert transport_b.navigate_calls == [spec_b.source_url, "https://x/front-axle-steering/407"]
