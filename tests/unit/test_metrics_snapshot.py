"""T518 — orchestration/metrics.py::query_metrics() (FR-070/FR-071, US4).

Estado de banco fabricado (contagens conhecidas) — leitura pura, sem worker
pool real. `groups_per_minute` verificado pela diferença entre dois
snapshots sucessivos."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from tests.support import AMAROK_CONTEXT

from amayama_scraper.checkpoint.checkpoint_entry import CheckpointEntry, CheckpointStatus
from amayama_scraper.checkpoint.collection_run import CollectionRun
from amayama_scraper.domain.identity import SpecIdentity
from amayama_scraper.orchestration.metrics import query_metrics
from amayama_scraper.orchestration.worker_pool import WorkerPoolConfig
from amayama_scraper.persistence.db import connect
from amayama_scraper.persistence.migrations.runner import run_migrations
from amayama_scraper.persistence.repositories import challenge_event_repo, worker_heartbeat_repo
from amayama_scraper.persistence.repositories.checkpoint_repo import (
    save_collection_run,
    upsert_checkpoint_entry,
)
from amayama_scraper.persistence.repositories.spec_registry_repo import save_spec_identity

_T0 = datetime(2026, 9, 3, 12, 0, 0, tzinfo=UTC)


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


def _conn():
    conn = connect(":memory:")
    run_migrations(conn)
    save_collection_run(conn, CollectionRun(run_id="run-1", scope=AMAROK_CONTEXT.scope()))
    return conn


def _accepted_entry(spec_key: str, group_id: str) -> CheckpointEntry:
    return CheckpointEntry(
        run_id="run-1",
        spec_key=spec_key,
        category_slug="cat",
        group_id=group_id,
        status=CheckpointStatus.ACCEPTED,
        completed_at=_T0,
    )


def test_snapshot_reflects_known_counts() -> None:
    conn = _conn()
    spec_a, spec_b = _spec(0), _spec(1)
    save_spec_identity(conn, spec_a)
    save_spec_identity(conn, spec_b)

    upsert_checkpoint_entry(conn, _accepted_entry(spec_a.stable_key(), "g1"))
    upsert_checkpoint_entry(conn, _accepted_entry(spec_a.stable_key(), "g2"))

    event_id = challenge_event_repo.record_observed(
        conn, run_id="run-1", worker_id="w0", capture_kind="GROUP_DETAIL", observed_at=_T0
    )
    challenge_event_repo.record_resolved(
        conn, event_id=event_id, resolved_at=_T0 + timedelta(seconds=15)
    )

    worker_heartbeat_repo.upsert_heartbeat(conn, run_id="run-1", worker_id="w0", pid=111, now=_T0)

    pool_config = WorkerPoolConfig(workers=3)
    snapshot = query_metrics(
        conn,
        run_id="run-1",
        context=AMAROK_CONTEXT,
        previous=None,
        previous_at=_T0,
        now=_T0,
        pool_config=pool_config,
    )

    assert snapshot.specs_completed == 0  # nenhuma alcançou current_state ainda
    assert snapshot.groups_accepted == 2
    assert snapshot.groups_per_minute == 0.0  # sem snapshot anterior
    assert snapshot.requests_total == 0  # nenhum raw_capture inserido neste teste
    assert snapshot.challenges_total == 1
    assert snapshot.challenges_per_hour == 1.0
    assert snapshot.challenge_wait_seconds_total == 15.0
    assert snapshot.active_workers == 1
    assert snapshot.effective_concurrency == 3  # lazy-init no teto configurado


def test_groups_per_minute_derived_from_successive_snapshots() -> None:
    conn = _conn()
    spec_a = _spec(0)
    save_spec_identity(conn, spec_a)
    pool_config = WorkerPoolConfig(workers=2)

    first = query_metrics(
        conn,
        run_id="run-1",
        context=AMAROK_CONTEXT,
        previous=None,
        previous_at=_T0,
        now=_T0,
        pool_config=pool_config,
    )
    assert first.groups_accepted == 0

    upsert_checkpoint_entry(conn, _accepted_entry(spec_a.stable_key(), "g1"))
    upsert_checkpoint_entry(conn, _accepted_entry(spec_a.stable_key(), "g2"))

    later = _T0 + timedelta(seconds=30)  # meio minuto depois
    second = query_metrics(
        conn,
        run_id="run-1",
        context=AMAROK_CONTEXT,
        previous=first,
        previous_at=_T0,
        now=later,
        pool_config=pool_config,
    )
    assert second.groups_accepted == 2
    # 2 grupos em 0.5 min => 4 grupos/min
    assert second.groups_per_minute == 4.0


def test_specs_completed_counts_only_specs_with_current_state() -> None:
    conn = _conn()
    spec_a, spec_b = _spec(0), _spec(1)
    save_spec_identity(conn, spec_a)
    save_spec_identity(conn, spec_b)
    conn.execute(
        "INSERT INTO current_spec_state (spec_identity_ref, latest_snapshot_id, cluster_key) "
        "VALUES (?, ?, NULL)",
        (spec_a.stable_key(), "snap-1"),
    )

    snapshot = query_metrics(
        conn,
        run_id="run-1",
        context=AMAROK_CONTEXT,
        previous=None,
        previous_at=_T0,
        now=_T0,
        pool_config=WorkerPoolConfig(workers=1),
    )
    assert snapshot.specs_completed == 1
