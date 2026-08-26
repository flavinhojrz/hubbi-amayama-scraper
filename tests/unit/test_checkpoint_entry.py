"""T034 — CheckpointEntry status enum + pure transition rules (data-model.md §11)."""

from datetime import UTC, datetime

import pytest

from amayama_scraper.checkpoint.checkpoint_entry import (
    CheckpointEntry,
    CheckpointEvent,
    CheckpointStatus,
    transition,
)


def test_pending_to_in_progress_on_start_attempt():
    assert (
        transition(CheckpointStatus.PENDING, CheckpointEvent.START_ATTEMPT)
        is CheckpointStatus.IN_PROGRESS
    )


def test_in_progress_to_accepted_on_accept():
    assert (
        transition(CheckpointStatus.IN_PROGRESS, CheckpointEvent.ACCEPT)
        is CheckpointStatus.ACCEPTED
    )


def test_in_progress_to_rejected_on_reject():
    assert (
        transition(CheckpointStatus.IN_PROGRESS, CheckpointEvent.REJECT)
        is CheckpointStatus.REJECTED
    )


def test_rejected_to_in_progress_on_retry():
    assert (
        transition(CheckpointStatus.REJECTED, CheckpointEvent.START_ATTEMPT)
        is CheckpointStatus.IN_PROGRESS
    )


def test_no_transition_out_of_accepted_any_event():
    for event in CheckpointEvent:
        assert transition(CheckpointStatus.ACCEPTED, event) is CheckpointStatus.ACCEPTED


def test_accept_without_in_progress_raises():
    with pytest.raises(ValueError):
        transition(CheckpointStatus.PENDING, CheckpointEvent.ACCEPT)


def test_reject_without_in_progress_raises():
    with pytest.raises(ValueError):
        transition(CheckpointStatus.PENDING, CheckpointEvent.REJECT)


def test_entry_key_is_the_unique_logical_key():
    entry = CheckpointEntry(run_id="r1", spec_key="s1", category_slug="c1", group_id="g1")
    assert entry.key == ("r1", "s1", "c1", "g1")


def test_accepted_entry_requires_completed_at():
    with pytest.raises(ValueError):
        CheckpointEntry(
            run_id="r1",
            spec_key="s1",
            category_slug="c1",
            group_id="g1",
            status=CheckpointStatus.ACCEPTED,
            completed_at=None,
        )


def test_accepted_entry_with_completed_at_is_valid():
    entry = CheckpointEntry(
        run_id="r1",
        spec_key="s1",
        category_slug="c1",
        group_id="g1",
        status=CheckpointStatus.ACCEPTED,
        completed_at=datetime(2026, 8, 26, tzinfo=UTC),
    )
    assert entry.status is CheckpointStatus.ACCEPTED
