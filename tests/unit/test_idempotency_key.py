"""T211 — idempotency_key = SHA256(run_id + spec_key + accepted_checkpoint_fingerprint)."""

from datetime import UTC, datetime

from amayama_scraper.checkpoint.checkpoint_entry import CheckpointEntry, CheckpointStatus
from amayama_scraper.fingerprints.canonical import domain_hash
from amayama_scraper.snapshots.idempotency import (
    accepted_checkpoint_fingerprint,
    compute_idempotency_key,
)


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


def test_matches_documented_formula():
    entries = [_entry("1", "cap-1")]
    expected = domain_hash(
        "amayama:snapshot-idempotency:v1\0",
        {
            "run_id": "run-1",
            "spec_key": "spec-1",
            "accepted_checkpoint_fingerprint": accepted_checkpoint_fingerprint(entries),
        },
    )
    assert compute_idempotency_key("run-1", "spec-1", entries) == expected


def test_deterministic():
    entries = [_entry("1", "cap-1")]
    assert compute_idempotency_key("run-1", "spec-1", entries) == compute_idempotency_key(
        "run-1", "spec-1", entries
    )
