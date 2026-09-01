"""T012 — build_scope_summary(): corpus saudável, spec sem snapshot, escopo vazio."""

from datetime import UTC, datetime

from amayama_scraper.analysis.summary import build_scope_summary
from amayama_scraper.analysis.types import ScopeIdentifier
from amayama_scraper.domain.identity import SpecIdentity
from amayama_scraper.snapshots.snapshot import SnapshotState, SpecSnapshot

SCOPE = ScopeIdentifier(manufacturer="VOLKSWAGEN", vehicle_model="AMAROK", market="AMA-BR")


def _identity(model_code: str, catalog_id: str) -> SpecIdentity:
    return SpecIdentity(
        source="AMAYAMA",
        manufacturer="VOLKSWAGEN",
        vehicle_model="AMAROK",
        market="AMA-BR",
        model_code=model_code,
        amayama_catalog_id=catalog_id,
        production_period_raw="2020-2021",
        source_url=f"https://amayama.example/{model_code}",
    )


def _snapshot(
    spec_ref: str,
    *,
    snapshot_id: str,
    counts: dict[str, int],
    state: SnapshotState = SnapshotState.VALID,
    collection_complete: bool = True,
) -> SpecSnapshot:
    return SpecSnapshot(
        snapshot_id=snapshot_id,
        spec_identity_ref=spec_ref,
        idempotency_key=f"idem-{snapshot_id}",
        collected_at=datetime(2026, 1, 1, tzinfo=UTC),
        parser_version="p1",
        normalizer_version="amayama-normalizer-v1",
        fingerprint_version="amayama-fingerprint-v1",
        collection_complete=collection_complete,
        structure_hash="s" * 64,
        spec_parts_hash="h" * 64,
        schema_semantic_hash="c" * 64,
        image_hash="i" * 64,
        state=state,
        counts=counts,
    )


def test_healthy_corpus_totals_and_distribution_match_counts_json():
    spec_a = _identity("A1", "100")
    spec_b = _identity("A2", "200")
    snap_a = _snapshot(
        spec_a.stable_key(),
        snapshot_id="snap-a",
        counts={"categories": 10, "groups": 30, "schemas": 100, "parts": 1500},
    )
    snap_b = _snapshot(
        spec_b.stable_key(),
        snapshot_id="snap-b",
        counts={"categories": 10, "groups": 20, "schemas": 80, "parts": 1000},
    )
    latest = {spec_a.stable_key(): snap_a, spec_b.stable_key(): snap_b}

    summary = build_scope_summary(SCOPE, [spec_a, spec_b], latest)

    assert summary.specs_discovered == 2
    assert summary.specs_valid_complete == 2
    assert summary.specs_incomplete_or_problematic == 0
    assert summary.categories_total == 20
    assert summary.groups_total == 50
    assert summary.schemas_total == 180
    assert summary.parts_total == 2500
    assert summary.specs_with_zero_parts == 0
    assert summary.specs_considered_for_distribution == 2
    assert summary.groups_per_spec.minimum == 20
    assert summary.groups_per_spec.maximum == 30
    assert summary.groups_per_spec.mean == 25.0
    assert summary.groups_per_spec.median == 25.0


def test_spec_without_snapshot_excluded_from_distribution():
    spec_with_snapshot = _identity("B1", "300")
    spec_without_snapshot = _identity("B2", "400")
    latest = {
        spec_with_snapshot.stable_key(): _snapshot(
            spec_with_snapshot.stable_key(),
            snapshot_id="snap-c",
            counts={"categories": 5, "groups": 10, "schemas": 40, "parts": 500},
        )
    }

    summary = build_scope_summary(SCOPE, [spec_with_snapshot, spec_without_snapshot], latest)

    assert summary.specs_discovered == 2
    assert summary.specs_valid_complete == 1
    assert summary.specs_incomplete_or_problematic == 1
    assert summary.specs_considered_for_distribution == 1
    assert summary.groups_per_spec.sample_size == 1


def test_zero_parts_spec_is_counted_but_not_an_error_at_summary_level():
    spec = _identity("2HBC34", "56058")
    latest = {
        spec.stable_key(): _snapshot(
            spec.stable_key(),
            snapshot_id="snap-zero",
            counts={"categories": 1, "groups": 1, "schemas": 1, "parts": 0},
        )
    }

    summary = build_scope_summary(SCOPE, [spec], latest)

    assert summary.specs_with_zero_parts == 1
    assert summary.parts_total == 0
    assert summary.specs_valid_complete == 1


def test_empty_scope_returns_zeros_without_exception():
    summary = build_scope_summary(SCOPE, [], {})

    assert summary.specs_discovered == 0
    assert summary.specs_valid_complete == 0
    assert summary.specs_incomplete_or_problematic == 0
    assert summary.specs_considered_for_distribution == 0
    assert summary.groups_per_spec.sample_size == 0
    assert summary.groups_per_spec.mean == 0.0
