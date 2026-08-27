"""T036 — SpecSnapshot fields, 5-state enum, idempotency_key, immutability."""

from datetime import UTC, datetime

import pytest

from amayama_scraper.snapshots.snapshot import SnapshotState, SpecSnapshot, assign_snapshot_state


def make_snapshot(**overrides: object) -> SpecSnapshot:
    defaults: dict[str, object] = dict(
        snapshot_id="snap-1",
        spec_identity_ref="stable-key-1",
        idempotency_key="idem-1",
        collected_at=datetime(2026, 8, 26, tzinfo=UTC),
        parser_version="amayama-parser-v1",
        normalizer_version="amayama-normalizer-v1",
        fingerprint_version="amayama-fingerprint-v1",
        collection_complete=True,
        structure_hash="a" * 64,
        spec_parts_hash="b" * 64,
        schema_semantic_hash="c" * 64,
        image_hash="d" * 64,
        state=SnapshotState.VALID,
    )
    defaults.update(overrides)
    return SpecSnapshot(**defaults)  # type: ignore[arg-type]


def test_five_states_exist():
    assert {s.value for s in SnapshotState} == {
        "VALID",
        "INCOMPLETE",
        "STALE",
        "SUPERSEDED",
        "INVALID",
    }


def test_is_frozen():
    snapshot = make_snapshot()
    with pytest.raises(Exception):  # noqa: B017
        snapshot.state = SnapshotState.STALE  # type: ignore[misc]


def test_assign_state_valid_when_complete_no_error():
    assert (
        assign_snapshot_state(has_critical_error=False, collection_complete=True)
        is SnapshotState.VALID
    )


def test_assign_state_incomplete_when_not_complete_no_error():
    assert (
        assign_snapshot_state(has_critical_error=False, collection_complete=False)
        is SnapshotState.INCOMPLETE
    )


def test_assign_state_invalid_when_critical_error():
    assert (
        assign_snapshot_state(has_critical_error=True, collection_complete=True)
        is SnapshotState.INVALID
    )


@pytest.mark.parametrize("field_name", ["snapshot_id", "idempotency_key", "structure_hash"])
def test_required_fields_cannot_be_empty(field_name: str) -> None:
    with pytest.raises(ValueError):
        make_snapshot(**{field_name: ""})
