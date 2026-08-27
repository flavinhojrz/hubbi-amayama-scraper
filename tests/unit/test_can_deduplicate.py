"""T141 — can_deduplicate() só é True com comparison_valid AND parts_relation == EXACT."""

from datetime import UTC, datetime

from amayama_scraper.equivalence.evaluate import can_deduplicate
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


def test_valid_and_exact_can_deduplicate():
    a = _snapshot(spec_parts_hash="same" * 16)
    b = _snapshot(spec_parts_hash="same" * 16)
    assert can_deduplicate(a, b, scope_a=SCOPE, scope_b=SCOPE) is True


def test_valid_but_different_cannot_deduplicate():
    a = _snapshot(spec_parts_hash="x" * 64)
    b = _snapshot(spec_parts_hash="y" * 64)
    assert can_deduplicate(a, b, scope_a=SCOPE, scope_b=SCOPE) is False


def test_invalid_comparison_cannot_deduplicate_even_if_hash_matches():
    a = _snapshot(spec_parts_hash="same" * 16)
    b = _snapshot(spec_parts_hash="same" * 16, state=SnapshotState.INVALID)
    assert can_deduplicate(a, b, scope_a=SCOPE, scope_b=SCOPE) is False
