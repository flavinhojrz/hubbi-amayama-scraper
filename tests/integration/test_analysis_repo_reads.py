"""T001/T003/T005/T007/T009 (003-corpus-analysis-tool) — leituras aditivas sobre SQLite real.

Mesmo padrão de tests/integration/test_checkpoint_repo.py: connect(":memory:")
+ run_migrations(), fixtures mínimas construídas via os próprios domain
types/repository functions já existentes.
"""

from datetime import UTC, datetime

import pytest

from amayama_scraper.domain.identity import SpecIdentity
from amayama_scraper.domain.manifest import ManifestCategory, ManifestGroupRef, SpecGroupManifest
from amayama_scraper.persistence.db import connect, connect_read_only
from amayama_scraper.persistence.migrations.runner import run_migrations
from amayama_scraper.persistence.repositories.manifest_repo import list_for_spec, save_manifest
from amayama_scraper.persistence.repositories.snapshot_repo import (
    UNAVAILABLE_HASH,
    list_latest_snapshot_per_spec,
    save_snapshot,
)
from amayama_scraper.persistence.repositories.spec_registry_repo import (
    list_by_scope,
    save_spec_identity,
)
from amayama_scraper.snapshots.snapshot import SnapshotState, SpecSnapshot


def _conn():
    conn = connect(":memory:")
    run_migrations(conn)
    return conn


def _identity(
    model_code: str, *, vehicle_model: str = "AMAROK", market: str = "AMA-BR"
) -> SpecIdentity:
    return SpecIdentity(
        source="AMAYAMA",
        manufacturer="VOLKSWAGEN",
        vehicle_model=vehicle_model,
        market=market,
        model_code=model_code,
        amayama_catalog_id="999",
        production_period_raw="2020-2021",
        source_url=f"https://amayama.example/{model_code}",
    )


def _snapshot(spec_ref: str, snapshot_id: str, collected_at: datetime) -> SpecSnapshot:
    return SpecSnapshot(
        snapshot_id=snapshot_id,
        spec_identity_ref=spec_ref,
        idempotency_key=f"idem-{snapshot_id}",
        collected_at=collected_at,
        parser_version="p1",
        normalizer_version="amayama-normalizer-v1",
        fingerprint_version="amayama-fingerprint-v1",
        collection_complete=True,
        structure_hash="s" * 64,
        spec_parts_hash="h" * 64,
        schema_semantic_hash="c" * 64,
        image_hash="i" * 64,
        state=SnapshotState.VALID,
        counts={"categories": 1, "groups": 1, "schemas": 1, "parts": 1},
    )


def test_list_by_scope_is_case_insensitive_and_excludes_other_scopes():
    conn = _conn()
    in_scope = _identity("SC1")
    other_market = _identity("SC2", market="AMA-OTHER")
    save_spec_identity(conn, in_scope)
    save_spec_identity(conn, other_market)

    result = list_by_scope(conn, manufacturer="volkswagen", vehicle_model="amarok", market="ama-br")

    assert [s.stable_key() for s in result] == [in_scope.stable_key()]


def test_list_latest_snapshot_per_spec_picks_most_recent_and_handles_empty_refs():
    conn = _conn()
    spec = _identity("SN1")
    save_spec_identity(conn, spec)
    older = _snapshot(spec.stable_key(), "snap-old", datetime(2026, 1, 1, tzinfo=UTC))
    newer = _snapshot(spec.stable_key(), "snap-new", datetime(2026, 6, 1, tzinfo=UTC))
    save_snapshot(conn, older)
    save_snapshot(conn, newer)

    result = list_latest_snapshot_per_spec(conn, [spec.stable_key()])
    assert result[spec.stable_key()].snapshot_id == "snap-new"

    assert list_latest_snapshot_per_spec(conn, []) == {}


def test_list_latest_snapshot_per_spec_tolerates_null_fingerprint_columns():
    """Codex finding #5 — um snapshot VALID/completo com hash NULL no banco
    (simulado via SQL direto, já que SpecSnapshot.__post_init__ recusaria
    construir um domain object assim) não pode crashar list_latest_snapshot_per_spec();
    o hash NULL deve virar UNAVAILABLE_HASH, nunca None nem uma string vazia."""
    conn = _conn()
    spec = _identity("NULLHASH1")
    save_spec_identity(conn, spec)
    conn.execute(
        """
        INSERT INTO spec_snapshot (
            snapshot_id, spec_identity_ref, idempotency_key, collected_at,
            parser_version, normalizer_version, collection_complete, state,
            counts_json, fingerprint_version, structure_hash, spec_parts_hash,
            schema_semantic_hash, image_hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL)
        """,
        (
            "snap-nullhash",
            spec.stable_key(),
            "idem-nullhash",
            "2026-01-01T00:00:00+00:00",
            "p1",
            "amayama-normalizer-v1",
            1,
            "VALID",
            '{"categories": 1, "groups": 1, "schemas": 1, "parts": 5}',
            "amayama-fingerprint-v1",
        ),
    )

    result = list_latest_snapshot_per_spec(conn, [spec.stable_key()])

    snapshot = result[spec.stable_key()]
    assert snapshot.state is SnapshotState.VALID
    assert snapshot.collection_complete is True
    assert snapshot.structure_hash == UNAVAILABLE_HASH
    assert snapshot.spec_parts_hash == UNAVAILABLE_HASH
    assert snapshot.schema_semantic_hash == UNAVAILABLE_HASH
    assert snapshot.image_hash == UNAVAILABLE_HASH


def test_list_for_spec_returns_all_manifests_with_run_id_most_recent_first():
    conn = _conn()
    spec = _identity("MF1")
    save_spec_identity(conn, spec)
    older = SpecGroupManifest(
        spec_key=spec.stable_key(),
        source_capture_id="cap-old",
        discovered_at=datetime(2026, 1, 1, tzinfo=UTC),
        categories=(ManifestCategory("engine", (ManifestGroupRef("1", "https://x/1"),)),),
        manifest_complete=True,
    )
    newer = SpecGroupManifest(
        spec_key=spec.stable_key(),
        source_capture_id="cap-new",
        discovered_at=datetime(2026, 6, 1, tzinfo=UTC),
        categories=(ManifestCategory("engine", (ManifestGroupRef("1", "https://x/1"),)),),
        manifest_complete=True,
    )
    save_manifest(conn, older, run_id="run-1")
    save_manifest(conn, newer, run_id="run-2")

    result = list_for_spec(conn, spec.stable_key())
    assert [(run_id, m.source_capture_id) for run_id, m in result] == [
        ("run-2", "cap-new"),
        ("run-1", "cap-old"),
    ]


def test_connect_read_only_never_creates_missing_file(tmp_path):
    missing_path = tmp_path / "does-not-exist.db"
    with pytest.raises(Exception):  # noqa: B017 - sqlite3.OperationalError, exact type not load-bearing
        connect_read_only(str(missing_path))
    assert not missing_path.exists()


def test_connect_read_only_reads_existing_data_without_writing(tmp_path):
    db_path = tmp_path / "existing.db"
    writer = connect(str(db_path))
    run_migrations(writer)
    spec = _identity("RO1")
    save_spec_identity(writer, spec)
    writer.close()

    reader = connect_read_only(str(db_path))
    try:
        result = list_by_scope(
            reader, manufacturer="VOLKSWAGEN", vehicle_model="AMAROK", market="AMA-BR"
        )
        assert len(result) == 1
        with pytest.raises(Exception):  # noqa: B017 - sqlite3.OperationalError: attempt to write a readonly database
            reader.execute("INSERT INTO spec_registry (stable_key) VALUES ('x')")
    finally:
        reader.close()
