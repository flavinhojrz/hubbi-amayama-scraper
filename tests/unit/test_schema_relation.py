"""T137 — schema_relation independente de parts_relation."""

from datetime import UTC, datetime

from amayama_scraper.equivalence.evaluate import evaluate_parts_relation, evaluate_schema_relation
from amayama_scraper.equivalence.types import PartsRelation, SchemaRelation
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


def test_schemas_exact_while_parts_differ():
    a = _snapshot(spec_parts_hash="p1" * 32, schema_semantic_hash="same" * 16)
    b = _snapshot(spec_parts_hash="p2" * 32, schema_semantic_hash="same" * 16)
    assert evaluate_schema_relation(a, b, scope_a=SCOPE, scope_b=SCOPE) is SchemaRelation.EXACT
    assert evaluate_parts_relation(a, b, scope_a=SCOPE, scope_b=SCOPE) is PartsRelation.DIFFERENT


def test_schemas_different_while_parts_exact():
    a = _snapshot(spec_parts_hash="same" * 16, schema_semantic_hash="s1" * 32)
    b = _snapshot(spec_parts_hash="same" * 16, schema_semantic_hash="s2" * 32)
    assert evaluate_schema_relation(a, b, scope_a=SCOPE, scope_b=SCOPE) is SchemaRelation.DIFFERENT
    assert evaluate_parts_relation(a, b, scope_a=SCOPE, scope_b=SCOPE) is PartsRelation.EXACT
