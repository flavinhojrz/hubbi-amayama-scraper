"""T233 — transição VALID → STALE quando revalidação detecta divergência sem nova
captura ainda aceita (data-model.md §6 máquina de estados)."""

from datetime import UTC, datetime

import pytest

from amayama_scraper.snapshots.snapshot import SnapshotState, SpecSnapshot, transition_to_stale


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


def test_valid_transitions_to_stale():
    snapshot = _snapshot()
    stale = transition_to_stale(snapshot)
    assert stale.state == SnapshotState.STALE
    # content/hashes are preserved — only state changes (immutability of history)
    assert stale.spec_parts_hash == snapshot.spec_parts_hash
    assert stale.snapshot_id == snapshot.snapshot_id


def test_only_valid_can_transition_to_stale():
    for state in (
        SnapshotState.INCOMPLETE,
        SnapshotState.INVALID,
        SnapshotState.STALE,
        SnapshotState.SUPERSEDED,
    ):
        with pytest.raises(ValueError):
            transition_to_stale(_snapshot(state=state))
