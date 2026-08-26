"""T223 — atribuição de state (VALID/INCOMPLETE/INVALID) conforme critical_error+
collection_complete (FR-027)."""

from amayama_scraper.snapshots.snapshot import SnapshotState, assign_snapshot_state


def test_valid_when_complete_and_no_critical_error():
    assert (
        assign_snapshot_state(has_critical_error=False, collection_complete=True)
        == SnapshotState.VALID
    )


def test_incomplete_when_not_complete_and_no_critical_error():
    assert (
        assign_snapshot_state(has_critical_error=False, collection_complete=False)
        == SnapshotState.INCOMPLETE
    )


def test_invalid_when_critical_error_regardless_of_completeness():
    assert (
        assign_snapshot_state(has_critical_error=True, collection_complete=True)
        == SnapshotState.INVALID
    )
    assert (
        assign_snapshot_state(has_critical_error=True, collection_complete=False)
        == SnapshotState.INVALID
    )
