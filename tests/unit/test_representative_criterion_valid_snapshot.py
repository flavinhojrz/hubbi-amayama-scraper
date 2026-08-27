"""T149 — critério 1 (snapshot válido) desclassifica candidatos não-VALID."""

from datetime import UTC, datetime

import pytest

from amayama_scraper.equivalence.representative import (
    NoValidCandidateError,
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


def test_non_valid_candidates_are_excluded():
    valid = _candidate(spec_identity_ref="spec-valid")
    incomplete = _candidate(
        spec_identity_ref="spec-incomplete", snapshot_state=SnapshotState.INCOMPLETE
    )
    result = select_representative((incomplete, valid))
    assert result == "spec-valid"


def test_no_valid_candidate_raises():
    incomplete = _candidate(snapshot_state=SnapshotState.INCOMPLETE)
    invalid = _candidate(snapshot_state=SnapshotState.INVALID)
    with pytest.raises(NoValidCandidateError):
        select_representative((incomplete, invalid))
