"""T225 — INCOMPLETE/INVALID nunca participam de avaliação de equivalência (FR-028).

Integra Phase 7 (is_comparison_valid) com os estados reais produzidos por
assign_snapshot_state() (Phase 13).
"""

from datetime import UTC, datetime

from amayama_scraper.equivalence.validity import is_comparison_valid
from amayama_scraper.snapshots.snapshot import SnapshotState, SpecSnapshot, assign_snapshot_state

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


def test_incomplete_snapshot_from_real_state_assignment_excluded():
    state = assign_snapshot_state(has_critical_error=False, collection_complete=False)
    assert state == SnapshotState.INCOMPLETE

    incomplete = _snapshot(state=state, collection_complete=False)
    valid = _snapshot(snapshot_id="snap-2")
    assert is_comparison_valid(incomplete, valid, scope_a=SCOPE, scope_b=SCOPE) is False
    assert is_comparison_valid(valid, incomplete, scope_a=SCOPE, scope_b=SCOPE) is False


def test_invalid_snapshot_from_real_state_assignment_excluded():
    state = assign_snapshot_state(has_critical_error=True, collection_complete=True)
    assert state == SnapshotState.INVALID

    invalid = _snapshot(state=state)
    valid = _snapshot(snapshot_id="snap-2")
    assert is_comparison_valid(invalid, valid, scope_a=SCOPE, scope_b=SCOPE) is False
    assert is_comparison_valid(valid, invalid, scope_a=SCOPE, scope_b=SCOPE) is False


def test_two_valid_snapshots_are_not_excluded():
    valid_a = _snapshot(snapshot_id="snap-a")
    valid_b = _snapshot(snapshot_id="snap-b")
    assert is_comparison_valid(valid_a, valid_b, scope_a=SCOPE, scope_b=SCOPE) is True
