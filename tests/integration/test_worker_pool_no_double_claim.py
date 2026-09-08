"""T513 — SC-002: dois workers (threads, cada um com sua PRÓPRIA
sqlite3.Connection para o MESMO arquivo real — mesma proteção de concorrência
entre processos reais, contracts/worker-pool-contract.md §0/§3) nunca
reivindicam a mesma spec ao mesmo tempo.

Threads (não `multiprocessing.Process`) por design de teste — cada uma com
conexão própria ao mesmo arquivo SQLite exercitam a MESMA serialização real
(`BEGIN IMMEDIATE` + WAL + busy_timeout) que dois processos de SO
exercitariam, sem a fragilidade/custo de spawn real em CI (tasks.md T513
explicitamente permite esta estratégia)."""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime
from pathlib import Path

from tests.support import AMAROK_CONTEXT

from amayama_scraper.checkpoint.collection_run import CollectionRun
from amayama_scraper.domain.identity import SpecIdentity
from amayama_scraper.orchestration.collection_driver import OperationalFilters
from amayama_scraper.orchestration.worker_pool import WorkerPoolConfig, next_claimable_spec
from amayama_scraper.persistence.db import connect
from amayama_scraper.persistence.migrations.runner import run_migrations
from amayama_scraper.persistence.repositories import lease_repo
from amayama_scraper.persistence.repositories.checkpoint_repo import save_collection_run
from amayama_scraper.persistence.repositories.spec_registry_repo import save_spec_identity

_N_SPECS = 12


def _make_spec(index: int) -> SpecIdentity:
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


def _mark_completed(conn, key: str) -> None:
    """Simula "spec processada" sem depender do driver real — o suficiente
    para exercitar a exclusão FR-024 dentro de next_claimable_spec() e dar
    término natural ao laço de cada worker."""
    conn.execute(
        "INSERT INTO current_spec_state (spec_identity_ref, latest_snapshot_id, cluster_key) "
        "VALUES (?, ?, NULL)",
        (key, "test-snapshot"),
    )


def test_two_workers_never_claim_the_same_spec_concurrently(tmp_path: Path) -> None:
    db_path = str(tmp_path / "pool.db")
    setup_conn = connect(db_path)
    run_migrations(setup_conn)
    save_collection_run(setup_conn, CollectionRun(run_id="run-1", scope=AMAROK_CONTEXT.scope()))
    specs = [_make_spec(i) for i in range(_N_SPECS)]
    for spec in specs:
        save_spec_identity(setup_conn, spec)
    setup_conn.close()

    pool_config = WorkerPoolConfig(workers=2)
    claims_by_worker: dict[str, list[str]] = {"worker-0": [], "worker-1": []}
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def run_worker(worker_id: str) -> None:
        try:
            conn = connect(db_path)
            barrier.wait()
            while True:
                result = next_claimable_spec(
                    conn,
                    run_id="run-1",
                    context=AMAROK_CONTEXT,
                    worker_id=worker_id,
                    filters=OperationalFilters(),
                    pool_config=pool_config,
                    pool_session_id="test-session",
                    now=datetime.now(UTC),
                )
                if result.claimed is None:
                    if result.throttled:
                        time.sleep(0.001)
                        continue
                    break
                key = result.claimed.spec.stable_key()
                claims_by_worker[worker_id].append(key)
                _mark_completed(conn, key)
                lease_repo.release_lease(
                    conn, run_id="run-1", spec_key=key, owner=worker_id, now=datetime.now(UTC)
                )
            conn.close()
        except BaseException as exc:  # noqa: BLE001 - surfaced to the main thread below
            errors.append(exc)

    threads = [
        threading.Thread(target=run_worker, args=(worker_id,))
        for worker_id in ("worker-0", "worker-1")
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert not errors, f"worker thread(s) raised: {errors}"

    all_claims = claims_by_worker["worker-0"] + claims_by_worker["worker-1"]
    assert len(all_claims) == _N_SPECS, "every spec must be claimed exactly once, by someone"
    assert len(set(all_claims)) == _N_SPECS, "no spec_key was claimed more than once (no overlap)"
    assert set(claims_by_worker["worker-0"]).isdisjoint(claims_by_worker["worker-1"])


def test_third_worker_beyond_effective_concurrency_never_claims(tmp_path: Path) -> None:
    """FR-062: com effective_concurrency == 1, um segundo worker nunca
    reivindica enquanto o primeiro detém um lease ativo — mesmo havendo
    specs disponíveis."""
    db_path = str(tmp_path / "pool.db")
    setup_conn = connect(db_path)
    run_migrations(setup_conn)
    save_collection_run(setup_conn, CollectionRun(run_id="run-1", scope=AMAROK_CONTEXT.scope()))
    specs = [_make_spec(i) for i in range(3)]
    for spec in specs:
        save_spec_identity(setup_conn, spec)
    setup_conn.close()

    # workers=1 -> effective_concurrency inicial == 1 (lazy-init, FR-060).
    pool_config = WorkerPoolConfig(workers=1)
    now = datetime.now(UTC)

    conn_a = connect(db_path)
    first = next_claimable_spec(
        conn_a,
        run_id="run-1",
        context=AMAROK_CONTEXT,
        worker_id="worker-0",
        filters=OperationalFilters(),
        pool_config=pool_config,
        pool_session_id="test-session",
        now=now,
    )
    assert first.claimed is not None

    conn_b = connect(db_path)
    second_attempt = next_claimable_spec(
        conn_b,
        run_id="run-1",
        context=AMAROK_CONTEXT,
        worker_id="worker-1",
        filters=OperationalFilters(),
        pool_config=pool_config,
        pool_session_id="test-session",
        now=now,
    )
    assert second_attempt.claimed is None
    assert second_attempt.throttled  # ainda há 2 specs pendentes, só sem slot agora (HIGH 5)
