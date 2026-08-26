"""T151 — critério 3 (catálogo mais atual via collected_at) — research.md §12."""

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


def test_tie_on_image_count_broken_by_more_recent_collected_at():
    older = _candidate(
        spec_identity_ref="spec-older", collected_at=datetime(2025, 1, 1, tzinfo=UTC)
    )
    newer = _candidate(
        spec_identity_ref="spec-newer", collected_at=datetime(2026, 6, 1, tzinfo=UTC)
    )
    assert select_representative((older, newer)) == "spec-newer"
