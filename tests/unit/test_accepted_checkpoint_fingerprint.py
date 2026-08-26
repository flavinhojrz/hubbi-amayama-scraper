"""T209 — accepted_checkpoint_fingerprint(): multiset determinístico de
(category_slug, group_id, raw_capture_id)."""

from datetime import UTC, datetime

from amayama_scraper.checkpoint.checkpoint_entry import CheckpointEntry, CheckpointStatus
from amayama_scraper.snapshots.idempotency import accepted_checkpoint_fingerprint


def _entry(group_id: str, raw_capture_id: str) -> CheckpointEntry:
    return CheckpointEntry(
        run_id="run-1",
        spec_key="spec-1",
        category_slug="engine",
        group_id=group_id,
        status=CheckpointStatus.ACCEPTED,
        raw_capture_id=raw_capture_id,
        completed_at=datetime.now(UTC),
    )


def test_order_of_entries_does_not_matter():
    a = accepted_checkpoint_fingerprint([_entry("1", "cap-1"), _entry("2", "cap-2")])
    b = accepted_checkpoint_fingerprint([_entry("2", "cap-2"), _entry("1", "cap-1")])
    assert a == b


def test_different_raw_capture_id_changes_the_fingerprint():
    a = accepted_checkpoint_fingerprint([_entry("1", "cap-1")])
    b = accepted_checkpoint_fingerprint([_entry("1", "cap-2")])
    assert a != b


def test_empty_list_produces_empty_multiset():
    assert accepted_checkpoint_fingerprint([]) == []
