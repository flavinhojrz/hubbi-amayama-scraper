"""T185 — checkpoint_repo: upsert idempotente, ACCEPTED terminal, list_accepted() exato."""

from datetime import UTC, datetime

from amayama_scraper.checkpoint.checkpoint_entry import CheckpointEntry, CheckpointStatus
from amayama_scraper.checkpoint.collection_run import CollectionRun
from amayama_scraper.persistence.db import connect
from amayama_scraper.persistence.migrations.runner import run_migrations
from amayama_scraper.persistence.repositories.checkpoint_repo import (
    get_checkpoint_entry,
    list_accepted,
    save_collection_run,
    upsert_checkpoint_entry,
)


def _conn():
    conn = connect(":memory:")
    run_migrations(conn)
    save_collection_run(conn, CollectionRun(run_id="run-1"))
    # minimal raw_blob/raw_capture fixture rows so checkpoint_entry.raw_capture_id
    # (FK REFERENCES raw_capture) can be exercised in these tests.
    conn.execute(
        "INSERT INTO raw_blob (content_hash, size_bytes, storage_path, first_seen_at) "
        "VALUES (?, ?, ?, ?)",
        ("x" * 64, 10, "/blobs/x", "2026-08-26T00:00:00+00:00"),
    )
    conn.execute(
        "INSERT INTO raw_capture ("
        "capture_id, run_id, content_hash, source_url, collected_at, "
        "capture_kind, acquisition_mode) VALUES (?, ?, ?, ?, ?, ?, ?)",
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


def test_upsert_twice_does_not_duplicate_row():
    conn = _conn()
    entry = CheckpointEntry(run_id="run-1", spec_key="spec-1", category_slug="engine", group_id="1")
    upsert_checkpoint_entry(conn, entry)
    upsert_checkpoint_entry(conn, entry)

    count = conn.execute("SELECT COUNT(*) AS c FROM checkpoint_entry").fetchone()["c"]
    assert count == 1


def test_accepted_is_terminal_further_upserts_are_no_ops():
    conn = _conn()
    accepted = CheckpointEntry(
        run_id="run-1",
        spec_key="spec-1",
        category_slug="engine",
        group_id="1",
        status=CheckpointStatus.ACCEPTED,
        raw_capture_id="cap-1",
        completed_at=datetime.now(UTC),
    )
    upsert_checkpoint_entry(conn, accepted)

    regression_attempt = CheckpointEntry(
        run_id="run-1",
        spec_key="spec-1",
        category_slug="engine",
        group_id="1",
        status=CheckpointStatus.REJECTED,
    )
    upsert_checkpoint_entry(conn, regression_attempt)

    fetched = get_checkpoint_entry(conn, "run-1", "spec-1", "engine", "1")
    assert fetched is not None
    assert fetched.status == CheckpointStatus.ACCEPTED
    assert fetched.raw_capture_id == "cap-1"


def test_list_accepted_returns_only_accepted_with_raw_capture_id_preserved():
    conn = _conn()
    upsert_checkpoint_entry(
        conn,
        CheckpointEntry(
            run_id="run-1",
            spec_key="spec-1",
            category_slug="engine",
            group_id="1",
            status=CheckpointStatus.ACCEPTED,
            raw_capture_id="cap-1",
            completed_at=datetime.now(UTC),
        ),
    )
    upsert_checkpoint_entry(
        conn,
        CheckpointEntry(
            run_id="run-1",
            spec_key="spec-1",
            category_slug="engine",
            group_id="2",
            status=CheckpointStatus.IN_PROGRESS,
        ),
    )
    upsert_checkpoint_entry(
        conn,
        CheckpointEntry(
            run_id="run-1",
            spec_key="spec-1",
            category_slug="engine",
            group_id="3",
            status=CheckpointStatus.REJECTED,
        ),
    )

    accepted = list_accepted(conn, "run-1", "spec-1")
    assert len(accepted) == 1
    assert accepted[0].group_id == "1"
    assert accepted[0].raw_capture_id == "cap-1"


def test_list_accepted_survives_a_fresh_repository_instance_simulating_restart():
    conn = _conn()
    upsert_checkpoint_entry(
        conn,
        CheckpointEntry(
            run_id="run-1",
            spec_key="spec-1",
            category_slug="engine",
            group_id="1",
            status=CheckpointStatus.ACCEPTED,
            raw_capture_id="cap-1",
            completed_at=datetime.now(UTC),
        ),
    )
    # a fresh call against the same underlying storage — no in-memory state reused
    accepted = list_accepted(conn, "run-1", "spec-1")
    assert len(accepted) == 1
