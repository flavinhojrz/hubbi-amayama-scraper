"""T134 — version mismatch: comparison_valid=False, parts_relation=UNKNOWN (nunca DIFFERENT)."""

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


def test_normalizer_version_mismatch_is_unknown_not_different():
    # spec_parts_hash intentionally differs too — must still be UNKNOWN, not DIFFERENT.
    a = _snapshot(spec_parts_hash="p" * 64)
    b = _snapshot(spec_parts_hash="q" * 64, normalizer_version="amayama-normalizer-v2")
    assert evaluate_parts_relation(a, b, scope_a=SCOPE, scope_b=SCOPE) is PartsRelation.UNKNOWN


def test_fingerprint_version_mismatch_is_unknown_not_different():
    a = _snapshot(spec_parts_hash="p" * 64)
    b = _snapshot(spec_parts_hash="q" * 64, fingerprint_version="amayama-fingerprint-v2")
    assert evaluate_parts_relation(a, b, scope_a=SCOPE, scope_b=SCOPE) is PartsRelation.UNKNOWN
