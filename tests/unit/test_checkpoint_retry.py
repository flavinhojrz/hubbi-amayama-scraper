"""T203 — retry após REJECTED incrementa attempt_count e permite nova tentativa."""

from amayama_scraper.checkpoint.checkpoint_entry import CheckpointEvent, CheckpointStatus
from amayama_scraper.checkpoint.collection_run import CollectionRun
from amayama_scraper.checkpoint.upsert import upsert_checkpoint
from amayama_scraper.persistence.db import connect
from amayama_scraper.persistence.migrations.runner import run_migrations
from amayama_scraper.persistence.repositories.checkpoint_repo import save_collection_run


def _conn():
    conn = connect(":memory:")
    run_migrations(conn)
    save_collection_run(conn, CollectionRun(run_id="run-1"))
    conn.execute(
        "INSERT INTO raw_blob (content_hash, size_bytes, storage_path, first_seen_at) "
        "VALUES (?, ?, ?, ?)",
        ("x" * 64, 10, "/blobs/x", "2026-08-26T00:00:00+00:00"),
    )
    conn.execute(
        "INSERT INTO raw_capture (capture_id, run_id, content_hash, source_url, "
        "collected_at, capture_kind, acquisition_mode) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            "cap-1",
            "run-1",
            "x" * 64,
            "https://x/407",
            "2026-08-26T00:00:00+00:00",
            "GROUP_DETAIL",
            "MANUAL_BROWSER",
        ),
    )
    return conn


def test_retry_after_rejected_increments_attempt_count_and_can_reach_accepted():
    conn = _conn()
    kwargs = dict(run_id="run-1", spec_key="spec-1", category_slug="engine", group_id="1")

    upsert_checkpoint(conn, event=CheckpointEvent.START_ATTEMPT, **kwargs)
    upsert_checkpoint(conn, event=CheckpointEvent.REJECT, **kwargs)

    retried = upsert_checkpoint(conn, event=CheckpointEvent.START_ATTEMPT, **kwargs)
    assert retried.status == CheckpointStatus.IN_PROGRESS
    assert retried.attempt_count == 2

    accepted = upsert_checkpoint(
        conn, event=CheckpointEvent.ACCEPT, raw_capture_id="cap-1", **kwargs
    )
    assert accepted.status == CheckpointStatus.ACCEPTED
    assert accepted.attempt_count == 2
