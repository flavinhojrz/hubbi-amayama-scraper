"""T143 — snapshots INCOMPLETE/INVALID nunca produzem comparison_valid == True (FR-028)."""

from datetime import UTC, datetime

import pytest

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


@pytest.mark.parametrize("state", [SnapshotState.INCOMPLETE, SnapshotState.INVALID])
def test_disqualifying_state_on_either_side_excludes_comparison(state: SnapshotState) -> None:
    valid = _snapshot()
    disqualified = _snapshot(
        state=state, collection_complete=(state is not SnapshotState.INCOMPLETE)
    )
    assert is_comparison_valid(valid, disqualified, scope_a=SCOPE, scope_b=SCOPE) is False
    assert is_comparison_valid(disqualified, valid, scope_a=SCOPE, scope_b=SCOPE) is False
