"""T514 — SC-003: um worker "morto" (lease criado e nunca renovado, expirado)
é recuperado por outro worker sem reprocessar grupos já ACCEPTED — via
`run_worker_loop()` real (com `FakeBrowserTransport`), não apenas
`next_claimable_spec()` isolado (T513 já cobre isso)."""

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
from amayama_scraper.persistence.repositories import lease_repo
from amayama_scraper.persistence.repositories.checkpoint_repo import (
    list_accepted,
    save_collection_run,
)
from amayama_scraper.persistence.repositories.current_state_repo import get_current_state
from amayama_scraper.persistence.repositories.snapshot_repo import get_snapshot
from amayama_scraper.persistence.repositories.spec_registry_repo import save_spec_identity
from amayama_scraper.snapshots.snapshot import SnapshotState
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


def test_expired_lease_is_recovered_without_losing_accepted_progress(tmp_path: Path) -> None:
    db_path = str(tmp_path / "pool.db")
    conn = connect(db_path)
    run_migrations(conn)
    save_collection_run(conn, CollectionRun(run_id="run-1", scope=AMAROK_CONTEXT.scope()))
    spec = _spec()
    save_spec_identity(conn, spec)
    key = spec.stable_key()

    t0 = datetime(2026, 9, 3, 12, 0, 0, tzinfo=UTC)
    pool_config = WorkerPoolConfig(workers=2, lease_seconds=60.0)

    # "Worker morto": adquire o lease e nunca renova/libera/processa nada.
    dead_worker_claimed = lease_repo.try_claim(
        conn, run_id="run-1", spec_key=key, owner="worker-dead", now=t0, lease_seconds=60.0
    )
    assert dead_worker_claimed

    # Antes de expirar, nenhum outro worker consegue reivindicar (SC-002/US2).
    still_locked = next_claimable_spec(
        conn,
        run_id="run-1",
        context=AMAROK_CONTEXT,
        worker_id="worker-alive",
        filters=OperationalFilters(),
        pool_config=pool_config,
        pool_session_id="test-session",
        now=t0 + timedelta(seconds=10),
    )
    assert still_locked.claimed is None
    assert still_locked.throttled  # ainda há lease ativo (do worker-dead) — não é terminal

    # Depois de expirar, outro worker processa a spec de ponta a ponta via
    # o loop real (SPEC_NAVIGATION -> GROUP_DETAIL -> finalize).
    blob_store = FilesystemRawBlobStore(tmp_path / "blobs", conn)
    capture_repo = SqliteRawCaptureRepository(conn)
    transport = FakeBrowserTransport()
    transport.queue_navigate(_capture(MANIFEST_HTML, spec.source_url))
    transport.queue_navigate(_capture(GROUP_HTML, "https://x/front-axle-steering/407"))

    after_expiry = t0 + timedelta(seconds=61)
    run_worker_loop(
        transport,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        context=AMAROK_CONTEXT,
        worker_id="worker-alive",
        filters=OperationalFilters(),
        pool_config=pool_config,
        pool_session_id="test-session",
        now=lambda: after_expiry,
        sleep=lambda _s: None,
    )

    assert lease_repo.get_lease_owner(conn, run_id="run-1", spec_key=key) == "worker-alive"
    current = get_current_state(conn, key)
    assert current is not None, "spec must have reached VALID via the recovering worker"
    snapshot = get_snapshot(conn, current.latest_snapshot_id)
    assert snapshot is not None and snapshot.state == SnapshotState.VALID

    # Nenhum grupo perdido/duplicado — exatamente 1 ACCEPTED para esta spec.
    accepted = list_accepted(conn, "run-1", key)
    assert len(accepted) == 1
