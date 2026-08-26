"""T135 — parts_relation EXACT/DIFFERENT/UNKNOWN a partir de spec_parts_hash."""

from datetime import UTC, datetime

from amayama_scraper.equivalence.evaluate import evaluate_parts_relation
from amayama_scraper.equivalence.types import PartsRelation
from amayama_scraper.snapshots.snapshot import SnapshotState, SpecSnapshot

SCOPE = "AMAYAMA:VOLKSWAGEN:AMAROK:AMA-BR"


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


def test_identical_spec_parts_hash_is_exact():
    a, b = _snapshot(spec_parts_hash="x" * 64), _snapshot(spec_parts_hash="x" * 64)
    assert evaluate_parts_relation(a, b, scope_a=SCOPE, scope_b=SCOPE) is PartsRelation.EXACT


def test_different_spec_parts_hash_is_different():
    a, b = _snapshot(spec_parts_hash="x" * 64), _snapshot(spec_parts_hash="y" * 64)
    assert evaluate_parts_relation(a, b, scope_a=SCOPE, scope_b=SCOPE) is PartsRelation.DIFFERENT


def test_invalid_comparison_is_unknown():
    a, b = _snapshot(), _snapshot(state=SnapshotState.INVALID)
    assert evaluate_parts_relation(a, b, scope_a=SCOPE, scope_b=SCOPE) is PartsRelation.UNKNOWN
