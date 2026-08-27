"""fingerprint_repo — get/update FingerprintSet columns on spec_snapshot (data-model.md §7).

Não listado como task de teste dedicada em tasks.md (T189/T190 não têm um
T-teste entre si), mas a Constitution exige teste para toda regra
estrutural — cobertura mínima adicionada por consistência.
"""

from datetime import UTC, datetime

from amayama_scraper.fingerprints.types import FingerprintSet
from amayama_scraper.persistence.db import connect
from amayama_scraper.persistence.migrations.runner import run_migrations
from amayama_scraper.persistence.repositories.fingerprint_repo import (
    get_fingerprint_set,
    update_fingerprint_set,
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
    save_snapshot(
        conn,
        SpecSnapshot(
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
        ),
    )
    return conn


def test_get_fingerprint_set_matches_what_was_saved():
    conn = _conn()
    result = get_fingerprint_set(conn, "snap-1")
    assert result == FingerprintSet(
        structure_hash="s" * 64,
        spec_parts_hash="p" * 64,
        schema_semantic_hash="c" * 64,
        image_hash="i" * 64,
        fingerprint_version="amayama-fingerprint-v1",
    )


def test_update_fingerprint_set_overwrites_all_four_hashes():
    conn = _conn()
    update_fingerprint_set(
        conn,
        "snap-1",
        FingerprintSet(
            structure_hash="s2" * 32,
            spec_parts_hash="p2" * 32,
            schema_semantic_hash="c2" * 32,
            image_hash="i2" * 32,
            fingerprint_version="amayama-fingerprint-v2",
        ),
    )
    result = get_fingerprint_set(conn, "snap-1")
    assert result is not None
    assert result.fingerprint_version == "amayama-fingerprint-v2"
    assert result.structure_hash == "s2" * 32


def test_missing_snapshot_returns_none():
    conn = _conn()
    assert get_fingerprint_set(conn, "nonexistent") is None
