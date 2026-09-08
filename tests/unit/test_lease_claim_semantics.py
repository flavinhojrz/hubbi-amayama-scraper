"""T505 — persistence/repositories/lease_repo.py (FR-020 a FR-025, SC-002/SC-003).

Conexão SQLite real em arquivo/memória — não é teste de domínio puro, é
contrato de transação (data-model.md §1). `try_claim`/`renew_lease`/
`release_lease` são exercitados sequencialmente sobre a mesma conexão; a
prova de concorrência real entre PROCESSOS distintos vive em
tests/integration/test_worker_pool_no_double_claim.py.
"""

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


def test_first_claim_succeeds() -> None:
    conn = _conn()
    assert lease_repo.try_claim(
        conn, run_id="run-1", spec_key="spec-a", owner="worker-0", now=_T0, lease_seconds=120
    )
    assert lease_repo.get_lease_owner(conn, run_id="run-1", spec_key="spec-a") == "worker-0"


def test_same_owner_can_reclaim_renewing_the_lease() -> None:
    conn = _conn()
    lease_repo.try_claim(
        conn, run_id="run-1", spec_key="spec-a", owner="worker-0", now=_T0, lease_seconds=120
    )
    later = _T0 + timedelta(seconds=30)
    assert lease_repo.try_claim(
        conn, run_id="run-1", spec_key="spec-a", owner="worker-0", now=later, lease_seconds=120
    )


def test_different_owner_cannot_claim_a_still_valid_lease() -> None:
    conn = _conn()
    lease_repo.try_claim(
        conn, run_id="run-1", spec_key="spec-a", owner="worker-0", now=_T0, lease_seconds=120
    )
    soon = _T0 + timedelta(seconds=10)
    assert not lease_repo.try_claim(
        conn, run_id="run-1", spec_key="spec-a", owner="worker-1", now=soon, lease_seconds=120
    )
    assert lease_repo.get_lease_owner(conn, run_id="run-1", spec_key="spec-a") == "worker-0"


def test_different_owner_recovers_an_expired_lease() -> None:
    """SC-003: worker morto (nunca renovou) — outro worker reivindica após expiração."""
    conn = _conn()
    lease_repo.try_claim(
        conn, run_id="run-1", spec_key="spec-a", owner="worker-0", now=_T0, lease_seconds=60
    )
    after_expiry = _T0 + timedelta(seconds=61)
    assert lease_repo.try_claim(
        conn,
        run_id="run-1",
        spec_key="spec-a",
        owner="worker-1",
        now=after_expiry,
        lease_seconds=60,
    )
    assert lease_repo.get_lease_owner(conn, run_id="run-1", spec_key="spec-a") == "worker-1"


def test_two_different_spec_keys_never_conflict() -> None:
    conn = _conn()
    assert lease_repo.try_claim(
        conn, run_id="run-1", spec_key="spec-a", owner="worker-0", now=_T0, lease_seconds=120
    )
    assert lease_repo.try_claim(
        conn, run_id="run-1", spec_key="spec-b", owner="worker-1", now=_T0, lease_seconds=120
    )


def test_renew_lease_extends_expiry_for_the_real_owner_only() -> None:
    conn = _conn()
    lease_repo.try_claim(
        conn, run_id="run-1", spec_key="spec-a", owner="worker-0", now=_T0, lease_seconds=60
    )
    renew_at = _T0 + timedelta(seconds=50)
    assert lease_repo.renew_lease(
        conn, run_id="run-1", spec_key="spec-a", owner="worker-0", now=renew_at, lease_seconds=60
    )
    # renewed past the original expiry (T0+60) — still owned by worker-0
    still_before_new_expiry = renew_at + timedelta(seconds=59)
    assert not lease_repo.try_claim(
        conn,
        run_id="run-1",
        spec_key="spec-a",
        owner="worker-1",
        now=still_before_new_expiry,
        lease_seconds=60,
    )


def test_renew_lease_by_non_owner_is_a_no_op() -> None:
    conn = _conn()
    lease_repo.try_claim(
        conn, run_id="run-1", spec_key="spec-a", owner="worker-0", now=_T0, lease_seconds=60
    )
    assert not lease_repo.renew_lease(
        conn,
        run_id="run-1",
        spec_key="spec-a",
        owner="worker-1",
        now=_T0 + timedelta(seconds=1),
        lease_seconds=60,
    )
    assert lease_repo.get_lease_owner(conn, run_id="run-1", spec_key="spec-a") == "worker-0"


def test_release_lease_makes_spec_immediately_reclaimable() -> None:
    """FR-025: liberação explícita nunca deleta (auditabilidade) — apenas
    expira o lease imediatamente, tornando-o reclamável no mesmo instante."""
    conn = _conn()
    lease_repo.try_claim(
        conn, run_id="run-1", spec_key="spec-a", owner="worker-0", now=_T0, lease_seconds=600
    )
    release_at = _T0 + timedelta(seconds=5)
    assert lease_repo.release_lease(
        conn, run_id="run-1", spec_key="spec-a", owner="worker-0", now=release_at
    )
    assert lease_repo.try_claim(
        conn,
        run_id="run-1",
        spec_key="spec-a",
        owner="worker-1",
        now=release_at,
        lease_seconds=600,
    )
    # audit trail preserved — row still exists, now owned by worker-1
    assert lease_repo.get_lease_owner(conn, run_id="run-1", spec_key="spec-a") == "worker-1"


def test_count_active_leases_excludes_expired_and_released() -> None:
    conn = _conn()
    lease_repo.try_claim(
        conn, run_id="run-1", spec_key="spec-a", owner="worker-0", now=_T0, lease_seconds=60
    )
    lease_repo.try_claim(
        conn, run_id="run-1", spec_key="spec-b", owner="worker-1", now=_T0, lease_seconds=60
    )
    assert lease_repo.count_active_leases(conn, run_id="run-1", now=_T0) == 2

    lease_repo.release_lease(conn, run_id="run-1", spec_key="spec-a", owner="worker-0", now=_T0)
    assert lease_repo.count_active_leases(conn, run_id="run-1", now=_T0) == 1

    long_after = _T0 + timedelta(seconds=1000)
    assert lease_repo.count_active_leases(conn, run_id="run-1", now=long_after) == 0
