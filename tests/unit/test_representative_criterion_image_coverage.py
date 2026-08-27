"""T150 — critério 2 (cobertura de imagens próprias, sem fallback) — research.md §12."""

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


def test_higher_own_image_count_wins():
    fewer = _candidate(spec_identity_ref="spec-fewer", own_image_count=1)
    more = _candidate(spec_identity_ref="spec-more", own_image_count=5)
    assert select_representative((fewer, more)) == "spec-more"
