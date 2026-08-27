"""T132 — is_comparison_valid(): scope, versões, collection_complete, estado apto."""

from datetime import UTC, datetime

from amayama_scraper.equivalence.validity import is_comparison_valid
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


def test_both_valid_same_scope_and_versions_is_valid():
    a, b = _snapshot(), _snapshot(snapshot_id="snap-2")
    assert is_comparison_valid(a, b, scope_a=SCOPE, scope_b=SCOPE) is True


def test_different_scope_is_invalid():
    a, b = _snapshot(), _snapshot()
    assert is_comparison_valid(a, b, scope_a=SCOPE, scope_b="OTHER:SCOPE") is False


def test_normalizer_version_mismatch_is_invalid():
    a = _snapshot()
    b = _snapshot(normalizer_version="amayama-normalizer-v2")
    assert is_comparison_valid(a, b, scope_a=SCOPE, scope_b=SCOPE) is False


def test_fingerprint_version_mismatch_is_invalid():
    a = _snapshot()
    b = _snapshot(fingerprint_version="amayama-fingerprint-v2")
    assert is_comparison_valid(a, b, scope_a=SCOPE, scope_b=SCOPE) is False


def test_collection_incomplete_is_invalid():
    a = _snapshot()
    b = _snapshot(collection_complete=False, state=SnapshotState.INCOMPLETE)
    assert is_comparison_valid(a, b, scope_a=SCOPE, scope_b=SCOPE) is False


def test_invalid_state_is_invalid():
    a = _snapshot()
    b = _snapshot(state=SnapshotState.INVALID)
    assert is_comparison_valid(a, b, scope_a=SCOPE, scope_b=SCOPE) is False


def test_superseded_state_is_invalid():
    a = _snapshot()
    b = _snapshot(state=SnapshotState.SUPERSEDED)
    assert is_comparison_valid(a, b, scope_a=SCOPE, scope_b=SCOPE) is False


def test_stale_state_is_acceptable():
    a = _snapshot(state=SnapshotState.STALE)
    b = _snapshot()
    assert is_comparison_valid(a, b, scope_a=SCOPE, scope_b=SCOPE) is True
