"""T214 — nova coleta legítima (novo raw_capture_id) produz idempotency_key diferente."""

from datetime import UTC, datetime

from amayama_scraper.checkpoint.checkpoint_entry import CheckpointEntry, CheckpointStatus
from amayama_scraper.snapshots.idempotency import compute_idempotency_key


def _entries(raw_capture_id: str) -> list[CheckpointEntry]:
    return [
        CheckpointEntry(
            run_id="run-1",
            spec_key="spec-1",
            category_slug="engine",
            group_id="1",
            status=CheckpointStatus.ACCEPTED,
            raw_capture_id=raw_capture_id,
            completed_at=datetime.now(UTC),
        )
    ]


def test_new_raw_capture_id_even_with_identical_content_produces_a_different_key():
    # even if the new capture's bytes are byte-for-byte identical (same
    # content_hash), it is a NEW RawCapture (Observation) with a new
    # capture_id — the idempotency key must reflect that as a new collection.
    original = compute_idempotency_key("run-1", "spec-1", _entries("cap-original"))
    recollected = compute_idempotency_key("run-1", "spec-1", _entries("cap-recollected"))
    assert original != recollected
