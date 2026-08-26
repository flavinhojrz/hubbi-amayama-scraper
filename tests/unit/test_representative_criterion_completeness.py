"""T152 — critério 4 (completude de metadados) — research.md §12."""

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


def test_tie_on_image_and_recency_broken_by_more_complete_metadata():
    same_time = datetime(2026, 1, 1, tzinfo=UTC)
    less = _candidate(
        spec_identity_ref="spec-less", collected_at=same_time, metadata_completeness_ratio=0.5
    )
    more = _candidate(
        spec_identity_ref="spec-more", collected_at=same_time, metadata_completeness_ratio=0.9
    )
    assert select_representative((less, more)) == "spec-more"
