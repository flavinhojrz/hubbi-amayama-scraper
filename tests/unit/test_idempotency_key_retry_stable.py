"""T213 — retry da mesma finalização produz o mesmo idempotency_key."""

from datetime import UTC, datetime

from amayama_scraper.checkpoint.checkpoint_entry import CheckpointEntry, CheckpointStatus
from amayama_scraper.snapshots.idempotency import compute_idempotency_key


def _entries() -> list[CheckpointEntry]:
    now = datetime.now(UTC)
    return [
        CheckpointEntry(
            run_id="run-1",
            spec_key="spec-1",
            category_slug="engine",
            group_id="1",
            status=CheckpointStatus.ACCEPTED,
            raw_capture_id="cap-1",
            completed_at=now,
        )
    ]


def test_same_accepted_set_retried_produces_the_same_key():
    first_attempt = compute_idempotency_key("run-1", "spec-1", _entries())
    second_attempt = compute_idempotency_key("run-1", "spec-1", _entries())
    assert first_attempt == second_attempt
