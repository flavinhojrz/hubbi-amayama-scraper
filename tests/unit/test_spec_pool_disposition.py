"""005 hardening (post-review, 2ª rodada) — BLOCKER 2:
`persistence/repositories/spec_pool_disposition_repo.py` no nível do
repositório. Conexão SQLite real."""

from __future__ import annotations

from datetime import UTC, datetime

from amayama_scraper.checkpoint.collection_run import CollectionRun
from amayama_scraper.persistence.db import connect
from amayama_scraper.persistence.migrations.runner import run_migrations
from amayama_scraper.persistence.repositories import spec_pool_disposition_repo as repo
from amayama_scraper.persistence.repositories.checkpoint_repo import save_collection_run

_T0 = datetime(2026, 9, 3, 12, 0, 0, tzinfo=UTC)


def _conn():
    conn = connect(":memory:")
    run_migrations(conn)
    save_collection_run(conn, CollectionRun(run_id="run-1"))
    return conn


def test_get_returns_none_when_no_disposition_recorded() -> None:
    conn = _conn()
    assert repo.get(conn, run_id="run-1", spec_key="spec-a") is None


def test_set_manual_retry_required_is_session_independent() -> None:
    conn = _conn()
    repo.set_manual_retry_required(conn, run_id="run-1", spec_key="spec-a", now=_T0)
    disposition = repo.get(conn, run_id="run-1", spec_key="spec-a")
    assert disposition is not None
    assert disposition.state == "MANUAL_RETRY_REQUIRED"
    assert disposition.pool_session_id is None


def test_set_deferred_this_session_records_the_session() -> None:
    conn = _conn()
    repo.set_deferred_this_session(
        conn, run_id="run-1", spec_key="spec-a", pool_session_id="session-1", now=_T0
    )
    disposition = repo.get(conn, run_id="run-1", spec_key="spec-a")
    assert disposition is not None
    assert disposition.state == "DEFERRED_THIS_SESSION"
    assert disposition.pool_session_id == "session-1"


def test_setting_a_new_disposition_overwrites_the_previous_one() -> None:
    conn = _conn()
    repo.set_deferred_this_session(
        conn, run_id="run-1", spec_key="spec-a", pool_session_id="session-1", now=_T0
    )
    repo.set_manual_retry_required(conn, run_id="run-1", spec_key="spec-a", now=_T0)
    disposition = repo.get(conn, run_id="run-1", spec_key="spec-a")
    assert disposition is not None
    assert disposition.state == "MANUAL_RETRY_REQUIRED"


def test_clear_removes_the_disposition() -> None:
    conn = _conn()
    repo.set_manual_retry_required(conn, run_id="run-1", spec_key="spec-a", now=_T0)
    repo.clear(conn, run_id="run-1", spec_key="spec-a")
    assert repo.get(conn, run_id="run-1", spec_key="spec-a") is None


def test_clear_on_a_never_recorded_spec_is_a_safe_no_op() -> None:
    conn = _conn()
    repo.clear(conn, run_id="run-1", spec_key="never-existed")  # não deve levantar
    assert repo.get(conn, run_id="run-1", spec_key="never-existed") is None


def test_dispositions_are_independent_per_spec_key() -> None:
    conn = _conn()
    repo.set_manual_retry_required(conn, run_id="run-1", spec_key="spec-a", now=_T0)
    assert repo.get(conn, run_id="run-1", spec_key="spec-b") is None
