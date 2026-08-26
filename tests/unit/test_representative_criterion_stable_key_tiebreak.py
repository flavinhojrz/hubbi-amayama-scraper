"""T153 — critério 5 (stable_key como desempate lexicográfico final) — research.md §12."""

from datetime import UTC, datetime

from amayama_scraper.equivalence.representative import (
    RepresentativeCandidate,
    select_representative,
)
from amayama_scraper.snapshots.snapshot import SnapshotState


def _candidate(**overrides: object) -> RepresentativeCandidate:
    defaults: dict[str, object] = dict(
        spec_identity_ref="spec-a",
        stable_key="a" * 64,
        snapshot_state=SnapshotState.VALID,
        own_image_count=0,
        collected_at=datetime(2026, 1, 1, tzinfo=UTC),
        metadata_completeness_ratio=1.0,
    )
    defaults.update(overrides)
    return RepresentativeCandidate(**defaults)  # type: ignore[arg-type]


def test_full_tie_broken_by_lexicographically_smaller_stable_key():
    same = dict(
        collected_at=datetime(2026, 1, 1, tzinfo=UTC),
        own_image_count=1,
        metadata_completeness_ratio=1.0,
    )
    lower = _candidate(spec_identity_ref="spec-lower", stable_key="a" * 64, **same)
    higher = _candidate(spec_identity_ref="spec-higher", stable_key="b" * 64, **same)
    assert select_representative((higher, lower)) == "spec-lower"
