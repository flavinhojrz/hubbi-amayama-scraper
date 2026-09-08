"""T523 — US3 fim-a-fim: um challenge real observado durante `run_worker_loop()`
(via `FakeBrowserTransport`) decrementa `effective_concurrency` (FR-063), e
um período estável subsequente o recupera em 1 nível (FR-064) — observável
via `rate_limiter_repo.read_state()`, com um clock inteiramente controlado
pelo teste (determinístico, SC-004)."""

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
from amayama_scraper.persistence.repositories import lease_repo, rate_limiter_repo
from amayama_scraper.persistence.repositories.checkpoint_repo import save_collection_run
from amayama_scraper.persistence.repositories.current_state_repo import get_current_state
from amayama_scraper.persistence.repositories.spec_registry_repo import save_spec_identity
from amayama_scraper.transport.port import BrowserCapture

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
CHALLENGE_HTML = (FIXTURES / "challenge_cloudflare.html").read_text(encoding="utf-8")

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


def test_challenge_decrements_and_stability_period_recovers_concurrency(tmp_path: Path) -> None:
    db_path = str(tmp_path / "pool.db")
    conn = connect(db_path)
    run_migrations(conn)
    save_collection_run(conn, CollectionRun(run_id="run-1", scope=AMAROK_CONTEXT.scope()))
    spec = _spec()
    save_spec_identity(conn, spec)

    t0 = datetime(2026, 9, 3, 12, 0, 0, tzinfo=UTC)
    clock = {"now": t0}

    pool_config = WorkerPoolConfig(
        workers=2, challenge_threshold=1, challenge_window_seconds=300.0, stability_seconds=600.0
    )

    # effective_concurrency começa no teto (2, lazy-init) antes de qualquer challenge.
    state_before = rate_limiter_repo.read_state(
        conn, run_id="run-1", config=pool_config.rate_limiter_config(), now=t0
    )
    assert state_before.effective_concurrency == 2

    blob_store = FilesystemRawBlobStore(tmp_path / "blobs", conn)
    capture_repo = SqliteRawCaptureRepository(conn)
    transport = FakeBrowserTransport()
    # SPEC_NAVIGATION inicial retorna challenge...
    transport.queue_navigate(_capture(CHALLENGE_HTML, spec.source_url))
    # ...o poll seguinte (current_capture, dentro de await_challenge_resolution) resolve.
    transport.queue_current_capture(_capture(MANIFEST_HTML, spec.source_url))
    transport.queue_navigate(_capture(GROUP_HTML, "https://x/front-axle-steering/407"))

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
        pool_session_id="test-session",
        poll_interval=0.0,
        sleep=lambda _s: None,
        now=lambda: clock["now"],
    )

    # a spec foi processada normalmente até VALID apesar do challenge (US3
    # nunca bloqueia o progresso — apenas ajusta a concorrência global).
    key = spec.stable_key()
    assert get_current_state(conn, key) is not None

    state_after_challenge = rate_limiter_repo.read_state(
        conn, run_id="run-1", config=pool_config.rate_limiter_config(), now=clock["now"]
    )
    assert state_after_challenge.effective_concurrency == 1  # FR-063: decrementou em 1

    # Nenhuma recuperação ainda — o período estável não decorreu.
    lease_repo.release_lease(  # já liberado por run_worker_loop, no-op aqui — defensivo
        conn, run_id="run-1", spec_key=key, owner="worker-0", now=clock["now"]
    )
    too_soon = clock["now"] + timedelta(seconds=1)
    still_degraded = next_claimable_spec(
        conn,
        run_id="run-1",
        context=AMAROK_CONTEXT,
        worker_id="worker-1",
        filters=OperationalFilters(),
        pool_config=pool_config,
        pool_session_id="test-session",
        now=too_soon,
    )
    # nada mais a reivindicar (única spec já VALID) — mas o estado do rate
    # limiter em si ainda não deve ter subido:
    state_too_soon = rate_limiter_repo.read_state(
        conn, run_id="run-1", config=pool_config.rate_limiter_config(), now=too_soon
    )
    assert state_too_soon.effective_concurrency == 1
    assert still_degraded.claimed is None
    assert not still_degraded.throttled  # spec única já VALID — terminal genuíno (HIGH 5)

    # Depois do período estável (stability_seconds), a checagem de claim
    # aplica a recuperação gradual (FR-064) — 1 nível, nunca acima do teto.
    after_stability = clock["now"] + timedelta(seconds=600)
    next_claimable_spec(
        conn,
        run_id="run-1",
        context=AMAROK_CONTEXT,
        worker_id="worker-1",
        filters=OperationalFilters(),
        pool_config=pool_config,
        pool_session_id="test-session",
        now=after_stability,
    )
    state_recovered = rate_limiter_repo.read_state(
        conn, run_id="run-1", config=pool_config.rate_limiter_config(), now=after_stability
    )
    assert state_recovered.effective_concurrency == 2  # de volta ao teto configurado
