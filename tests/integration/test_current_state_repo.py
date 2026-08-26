"""T197 — current_state_repo reflete o SpecSnapshot VALID/STALE mais recente + cluster_key."""

from datetime import UTC, datetime

from amayama_scraper.equivalence.cluster_types import ClusterAssignment
from amayama_scraper.persistence.db import connect
from amayama_scraper.persistence.migrations.runner import run_migrations
from amayama_scraper.persistence.repositories.cluster_repo import assign
from amayama_scraper.persistence.repositories.current_state_repo import (
    get_current_state,
    materialize,
)
from amayama_scraper.persistence.repositories.snapshot_repo import save_snapshot
from amayama_scraper.snapshots.snapshot import SnapshotState, SpecSnapshot


def _conn():
    conn = connect(":memory:")
    run_migrations(conn)
    conn.execute(
        "INSERT INTO spec_registry (stable_key, source, manufacturer, vehicle_model, "
        "market, model_code, amayama_catalog_id, production_period_raw, source_url) "
        "VALUES ('spec-1', 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H')"
    )
    return conn


def _snapshot(**overrides: object) -> SpecSnapshot:
    defaults: dict[str, object] = dict(
        snapshot_id="snap-1",
        spec_identity_ref="spec-1",
        idempotency_key="idem-1",
        collected_at=datetime(2026, 1, 1, tzinfo=UTC),
        parser_version="amayama-parser-v1",
        normalizer_version="amayama-normalizer-v1",
        fingerprint_version="amayama-fingerprint-v1",
        collection_complete=True,
        structure_hash="s" * 64,
        spec_parts_hash="p" * 64,
        schema_semantic_hash="c" * 64,
        image_hash="i" * 64,
        state=SnapshotState.VALID,
    )
    defaults.update(overrides)
    return SpecSnapshot(**defaults)  # type: ignore[arg-type]


def test_materialize_picks_the_most_recent_valid_snapshot():
    conn = _conn()
    save_snapshot(conn, _snapshot(snapshot_id="snap-old", idempotency_key="idem-old"))
    save_snapshot(
        conn,
        _snapshot(
            snapshot_id="snap-new",
            idempotency_key="idem-new",
            collected_at=datetime(2026, 6, 1, tzinfo=UTC),
        ),
    )

    state = materialize(conn, "spec-1")
    assert state is not None
    assert state.latest_snapshot_id == "snap-new"


def test_materialize_reflects_current_cluster_key():
    conn = _conn()
    save_snapshot(conn, _snapshot())
    assign(
        conn,
        ClusterAssignment(
            spec_identity_ref="spec-1",
            cluster_key="cluster-a",
            normalizer_version="v1",
            fingerprint_version="v1",
        ),
    )
    state = materialize(conn, "spec-1")
    assert state is not None
    assert state.cluster_key == "cluster-a"


def test_incomplete_or_invalid_snapshots_are_never_picked():
    conn = _conn()
    save_snapshot(conn, _snapshot(state=SnapshotState.INCOMPLETE))
    assert materialize(conn, "spec-1") is None


def test_materialize_is_reconstructible_and_persisted_as_a_projection():
    conn = _conn()
    save_snapshot(conn, _snapshot())
    materialize(conn, "spec-1")

    fetched = get_current_state(conn, "spec-1")
    assert fetched is not None
    assert fetched.latest_snapshot_id == "snap-1"
