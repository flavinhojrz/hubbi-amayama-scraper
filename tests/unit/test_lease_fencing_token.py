"""005 hardening (post-review) — BLOCKER 1 (fencing token) e
`list_active_lease_spec_keys()` no nível do repositório
(`persistence/repositories/lease_repo.py`). Conexão SQLite real.

Terminalidade/reclaim (BLOCKER 2) é decidida por
`spec_pool_disposition_repo.py` (nunca por backoff temporal de lease) —
ver `tests/unit/test_spec_pool_disposition.py` e
`tests/integration/test_worker_pool_no_infinite_reclaim.py`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from amayama_scraper.checkpoint.collection_run import CollectionRun
from amayama_scraper.persistence.db import connect
from amayama_scraper.persistence.migrations.runner import run_migrations
from amayama_scraper.persistence.repositories import lease_repo
from amayama_scraper.persistence.repositories.checkpoint_repo import save_collection_run

_T0 = datetime(2026, 9, 3, 12, 0, 0, tzinfo=UTC)


def _conn():
    conn = connect(":memory:")
    run_migrations(conn)
    save_collection_run(conn, CollectionRun(run_id="run-1"))
    return conn


def test_first_claim_returns_a_token_and_it_matches_get_lease_token() -> None:
    conn = _conn()
    token = lease_repo.try_claim(
        conn, run_id="run-1", spec_key="spec-a", owner="worker-0", now=_T0, lease_seconds=120
    )
    assert token is not None and token >= 1
    assert lease_repo.get_lease_token(conn, run_id="run-1", spec_key="spec-a") == (
        "worker-0",
        token,
    )


def test_each_successful_claim_or_renewal_produces_a_strictly_greater_token() -> None:
    conn = _conn()
    t1 = lease_repo.try_claim(
        conn, run_id="run-1", spec_key="spec-a", owner="worker-0", now=_T0, lease_seconds=120
    )
    t2 = lease_repo.renew_lease(
        conn,
        run_id="run-1",
        spec_key="spec-a",
        owner="worker-0",
        now=_T0 + timedelta(seconds=10),
        lease_seconds=120,
    )
    t3 = lease_repo.try_claim(
        conn,
        run_id="run-1",
        spec_key="spec-a",
        owner="worker-0",
        now=_T0 + timedelta(seconds=20),
        lease_seconds=120,
    )
    assert t1 is not None and t2 is not None and t3 is not None
    assert t1 < t2 < t3


def test_takeover_after_expiry_produces_a_new_and_greater_token_than_the_dead_worker_held() -> None:
    conn = _conn()
    old_token = lease_repo.try_claim(
        conn, run_id="run-1", spec_key="spec-a", owner="worker-dead", now=_T0, lease_seconds=60
    )
    assert old_token is not None
    new_token = lease_repo.try_claim(
        conn,
        run_id="run-1",
        spec_key="spec-a",
        owner="worker-alive",
        now=_T0 + timedelta(seconds=61),
        lease_seconds=60,
    )
    assert new_token is not None
    assert new_token > old_token
    assert lease_repo.get_lease_token(conn, run_id="run-1", spec_key="spec-a") == (
        "worker-alive",
        new_token,
    )
    # o token que o worker morto detinha nunca mais confere com o estado atual
    assert lease_repo.get_lease_token(conn, run_id="run-1", spec_key="spec-a") != (
        "worker-dead",
        old_token,
    )


def test_renew_lease_by_non_owner_returns_none_and_does_not_bump_token() -> None:
    conn = _conn()
    token = lease_repo.try_claim(
        conn, run_id="run-1", spec_key="spec-a", owner="worker-0", now=_T0, lease_seconds=120
    )
    result = lease_repo.renew_lease(
        conn,
        run_id="run-1",
        spec_key="spec-a",
        owner="worker-1",
        now=_T0 + timedelta(seconds=1),
        lease_seconds=120,
    )
    assert result is None
    assert lease_repo.get_lease_token(conn, run_id="run-1", spec_key="spec-a") == (
        "worker-0",
        token,
    )


def test_renew_lease_fails_after_takeover_even_for_the_original_owner() -> None:
    """O cenário central do BLOCKER 1: A detém o lease, expira, B recupera —
    A tentar renovar depois disso (ex.: um heartbeat atrasado) deve falhar,
    nunca reviver a posse de A silenciosamente."""
    conn = _conn()
    lease_repo.try_claim(
        conn, run_id="run-1", spec_key="spec-a", owner="worker-A", now=_T0, lease_seconds=60
    )
    lease_repo.try_claim(
        conn,
        run_id="run-1",
        spec_key="spec-a",
        owner="worker-B",
        now=_T0 + timedelta(seconds=61),
        lease_seconds=60,
    )
    late_renew = lease_repo.renew_lease(
        conn,
        run_id="run-1",
        spec_key="spec-a",
        owner="worker-A",
        now=_T0 + timedelta(seconds=62),
        lease_seconds=60,
    )
    assert late_renew is None
    assert lease_repo.get_lease_owner(conn, run_id="run-1", spec_key="spec-a") == "worker-B"


def test_list_active_lease_spec_keys_excludes_expired_and_released() -> None:
    conn = _conn()
    lease_repo.try_claim(
        conn, run_id="run-1", spec_key="spec-a", owner="worker-0", now=_T0, lease_seconds=60
    )
    lease_repo.try_claim(
        conn, run_id="run-1", spec_key="spec-b", owner="worker-1", now=_T0, lease_seconds=60
    )
    assert lease_repo.list_active_lease_spec_keys(conn, run_id="run-1", now=_T0) == {
        "spec-a",
        "spec-b",
    }
    lease_repo.release_lease(conn, run_id="run-1", spec_key="spec-a", owner="worker-0", now=_T0)
    assert lease_repo.list_active_lease_spec_keys(conn, run_id="run-1", now=_T0) == {"spec-b"}
