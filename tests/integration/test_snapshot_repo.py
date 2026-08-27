"""T188 — snapshot_repo idempotente: mesmo idempotency_key não insere segunda linha."""

from datetime import UTC, datetime

from amayama_scraper.persistence.db import connect
from amayama_scraper.persistence.migrations.runner import run_migrations
from amayama_scraper.persistence.repositories.snapshot_repo import (
    get_by_idempotency_key,
    get_snapshot,
    save_snapshot,
    supersede,
)
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
        collected_at=datetime.now(UTC),
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


def test_save_then_get_round_trips():
    conn = _conn()
    snapshot = _snapshot()
    save_snapshot(conn, snapshot)

    fetched = get_snapshot(conn, "snap-1")
    assert fetched == snapshot


def test_same_idempotency_key_does_not_insert_a_second_row():
    conn = _conn()
    save_snapshot(conn, _snapshot(snapshot_id="snap-1"))
    returned_id = save_snapshot(conn, _snapshot(snapshot_id="snap-2"))  # same idempotency_key

    assert returned_id == "snap-1"  # the ALREADY-EXISTING snapshot, never the new attempt
    count = conn.execute("SELECT COUNT(*) AS c FROM spec_snapshot").fetchone()["c"]
    assert count == 1
    assert get_snapshot(conn, "snap-2") is None


def test_get_by_idempotency_key():
    conn = _conn()
    save_snapshot(conn, _snapshot())
    fetched = get_by_idempotency_key(conn, "idem-1")
    assert fetched is not None
    assert fetched.snapshot_id == "snap-1"


def test_supersede_updates_state():
    conn = _conn()
    save_snapshot(conn, _snapshot())
    supersede(conn, "snap-1")
    fetched = get_snapshot(conn, "snap-1")
    assert fetched is not None
    assert fetched.state == SnapshotState.SUPERSEDED
