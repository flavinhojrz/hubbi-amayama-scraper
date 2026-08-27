"""T193 — cluster_repo invalida assignments antigos quando a versão muda."""

from amayama_scraper.equivalence.cluster_types import ClusterAssignment
from amayama_scraper.persistence.db import connect
from amayama_scraper.persistence.migrations.runner import run_migrations
from amayama_scraper.persistence.repositories.cluster_repo import (
    assign,
    get_assignment,
    list_members,
)


def _conn():
    conn = connect(":memory:")
    run_migrations(conn)
    for stable_key in ("spec-1", "spec-2"):
        conn.execute(
            "INSERT INTO spec_registry (stable_key, source, manufacturer, vehicle_model, "
            "market, model_code, amayama_catalog_id, production_period_raw, source_url) "
            "VALUES (?, 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H')",
            (stable_key,),
        )
    return conn


def test_assign_then_get_round_trips():
    conn = _conn()
    assignment = ClusterAssignment(
        spec_identity_ref="spec-1",
        cluster_key="cluster-a",
        normalizer_version="v1",
        fingerprint_version="v1",
    )
    assign(conn, assignment)
    assert get_assignment(conn, "spec-1") == assignment


def test_reassigning_under_a_new_version_overwrites_the_old_assignment():
    conn = _conn()
    assign(
        conn,
        ClusterAssignment(
            spec_identity_ref="spec-1",
            cluster_key="cluster-old",
            normalizer_version="v1",
            fingerprint_version="v1",
        ),
    )
    assign(
        conn,
        ClusterAssignment(
            spec_identity_ref="spec-1",
            cluster_key="cluster-new",
            normalizer_version="v2",
            fingerprint_version="v2",
        ),
    )

    fetched = get_assignment(conn, "spec-1")
    assert fetched is not None
    assert fetched.cluster_key == "cluster-new"
    assert fetched.normalizer_version == "v2"

    count = conn.execute("SELECT COUNT(*) AS c FROM cluster_assignment").fetchone()["c"]
    assert count == 1  # no stale row left behind


def test_list_members_of_a_cluster():
    conn = _conn()
    assign(
        conn,
        ClusterAssignment(
            spec_identity_ref="spec-1",
            cluster_key="cluster-a",
            normalizer_version="v1",
            fingerprint_version="v1",
        ),
    )
    assign(
        conn,
        ClusterAssignment(
            spec_identity_ref="spec-2",
            cluster_key="cluster-a",
            normalizer_version="v1",
            fingerprint_version="v1",
        ),
    )
    assert list_members(conn, "cluster-a") == ["spec-1", "spec-2"]
