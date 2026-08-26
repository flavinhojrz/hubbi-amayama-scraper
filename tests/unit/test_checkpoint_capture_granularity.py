"""T207 — raw_capture_id de um CheckpointEntry tipicamente corresponde a UM grupo
(research.md §16), mas o modelo continua permitindo compartilhamento entre grupos."""

from datetime import UTC, datetime

from amayama_scraper.checkpoint.checkpoint_entry import CheckpointEntry, CheckpointStatus


def test_typical_case_one_capture_per_group():
    now = datetime.now(UTC)
    a = CheckpointEntry(
        run_id="r",
        spec_key="s",
        category_slug="engine",
        group_id="1",
        status=CheckpointStatus.ACCEPTED,
        raw_capture_id="cap-1",
        completed_at=now,
    )
    assert a.raw_capture_id == "cap-1"


def test_model_still_permits_sharing_a_capture_across_groups():
    now = datetime.now(UTC)
    a = CheckpointEntry(
        run_id="r",
        spec_key="s",
        category_slug="engine",
        group_id="1",
        status=CheckpointStatus.ACCEPTED,
        raw_capture_id="cap-shared",
        completed_at=now,
    )
    b = CheckpointEntry(
        run_id="r",
        spec_key="s",
        category_slug="engine",
        group_id="2",
        status=CheckpointStatus.ACCEPTED,
        raw_capture_id="cap-shared",
        completed_at=now,
    )
    # nothing in the domain model forbids two distinct groups referencing
    # the same raw_capture_id (a future multi-group capture aggregation)
    assert a.raw_capture_id == b.raw_capture_id
    assert a.key != b.key
