"""Cobertura direta de rate_limiter_repo/challenge_event_repo/worker_heartbeat_repo
(T506-T508) — repositórios finos sobre a migration 0009 (data-model.md §2-§4).
Complementa T505 (lease_repo); Constitution §12 exige teste para toda regra
estrutural, incluindo estas (lazy-init, janela de tempo, staleness)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from amayama_scraper.checkpoint.collection_run import CollectionRun
from amayama_scraper.orchestration.rate_limiter import RateLimiterConfig, RateLimiterState
from amayama_scraper.persistence.db import connect
from amayama_scraper.persistence.migrations.runner import run_migrations
from amayama_scraper.persistence.repositories import (
    challenge_event_repo,
    rate_limiter_repo,
    worker_heartbeat_repo,
)
from amayama_scraper.persistence.repositories.checkpoint_repo import save_collection_run

_T0 = datetime(2026, 9, 3, 12, 0, 0, tzinfo=UTC)


def _conn():
    conn = connect(":memory:")
    run_migrations(conn)
    save_collection_run(conn, CollectionRun(run_id="run-1"))
    return conn


def _config() -> RateLimiterConfig:
    return RateLimiterConfig(
        max_concurrency=3,
        challenge_window_seconds=300.0,
        challenge_threshold=1,
        stability_seconds=600.0,
    )


# --- rate_limiter_repo ------------------------------------------------------


def test_read_state_lazy_inits_at_max_concurrency() -> None:
    conn = _conn()
    state = rate_limiter_repo.read_state(conn, run_id="run-1", config=_config(), now=_T0)
    assert state.effective_concurrency == 3
    assert state.stable_since == _T0


def test_read_state_after_lazy_init_persists_across_reads() -> None:
    conn = _conn()
    rate_limiter_repo.read_state(conn, run_id="run-1", config=_config(), now=_T0)
    second_read = rate_limiter_repo.read_state(
        conn, run_id="run-1", config=_config(), now=_T0 + timedelta(seconds=999)
    )
    # second read is a plain read of the already-persisted row — never re-inits
    assert second_read.effective_concurrency == 3
    assert second_read.stable_since == _T0


def test_write_state_round_trips() -> None:
    conn = _conn()
    written = RateLimiterState(effective_concurrency=1, stable_since=_T0)
    rate_limiter_repo.write_state(conn, run_id="run-1", state=written, now=_T0)
    read_back = rate_limiter_repo.read_state(conn, run_id="run-1", config=_config(), now=_T0)
    assert read_back == written


# --- challenge_event_repo ----------------------------------------------------


def test_record_observed_counts_within_window_only() -> None:
    conn = _conn()
    challenge_event_repo.record_observed(
        conn, run_id="run-1", worker_id="w0", capture_kind="GROUP_DETAIL", observed_at=_T0
    )
    now = _T0 + timedelta(seconds=100)
    assert (
        challenge_event_repo.count_in_window(conn, run_id="run-1", now=now, window_seconds=300) == 1
    )
    far_future = _T0 + timedelta(seconds=1000)
    assert (
        challenge_event_repo.count_in_window(
            conn, run_id="run-1", now=far_future, window_seconds=300
        )
        == 0
    )


def test_count_total_and_trailing_hour() -> None:
    conn = _conn()
    challenge_event_repo.record_observed(
        conn, run_id="run-1", worker_id="w0", capture_kind="MARKET_INDEX", observed_at=_T0
    )
    challenge_event_repo.record_observed(
        conn,
        run_id="run-1",
        worker_id="w1",
        capture_kind="GROUP_DETAIL",
        observed_at=_T0 + timedelta(hours=2),
    )
    assert challenge_event_repo.count_total(conn, run_id="run-1") == 2
    now = _T0 + timedelta(hours=2, minutes=1)
    assert challenge_event_repo.count_in_trailing_hour(conn, run_id="run-1", now=now) == 1


def test_total_wait_seconds_sums_only_resolved_events() -> None:
    conn = _conn()
    event_id = challenge_event_repo.record_observed(
        conn, run_id="run-1", worker_id="w0", capture_kind="GROUP_DETAIL", observed_at=_T0
    )
    # a second, still-open event never contributes to the sum
    challenge_event_repo.record_observed(
        conn,
        run_id="run-1",
        worker_id="w0",
        capture_kind="GROUP_DETAIL",
        observed_at=_T0 + timedelta(seconds=10),
    )
    challenge_event_repo.record_resolved(
        conn, event_id=event_id, resolved_at=_T0 + timedelta(seconds=30)
    )
    assert challenge_event_repo.total_wait_seconds(conn, run_id="run-1") == 30.0


# --- worker_heartbeat_repo ----------------------------------------------------


def test_count_active_respects_staleness_window() -> None:
    conn = _conn()
    worker_heartbeat_repo.upsert_heartbeat(conn, run_id="run-1", worker_id="w0", pid=111, now=_T0)
    assert (
        worker_heartbeat_repo.count_active(
            conn, run_id="run-1", now=_T0 + timedelta(seconds=10), staleness_seconds=30
        )
        == 1
    )
    assert (
        worker_heartbeat_repo.count_active(
            conn, run_id="run-1", now=_T0 + timedelta(seconds=60), staleness_seconds=30
        )
        == 0
    )


def test_upsert_heartbeat_updates_last_heartbeat_for_same_worker() -> None:
    conn = _conn()
    worker_heartbeat_repo.upsert_heartbeat(conn, run_id="run-1", worker_id="w0", pid=111, now=_T0)
    later = _T0 + timedelta(seconds=20)
    worker_heartbeat_repo.upsert_heartbeat(conn, run_id="run-1", worker_id="w0", pid=111, now=later)
    # still exactly one active worker row (no duplicate), fresh as of `later`
    assert (
        worker_heartbeat_repo.count_active(conn, run_id="run-1", now=later, staleness_seconds=5)
        == 1
    )
