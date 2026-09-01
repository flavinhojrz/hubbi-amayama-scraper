"""T185 — checkpoint_repo: upsert idempotente, ACCEPTED terminal, list_accepted() exato.

T026 (002) — list_incomplete_runs() (data-model.md §7, DEC-005): leitura
aditiva sobre collection_run, nenhuma migration, nenhuma função existente
alterada.
"""

from datetime import UTC, datetime

from amayama_scraper.checkpoint.checkpoint_entry import CheckpointEntry, CheckpointStatus
from amayama_scraper.checkpoint.collection_run import FIXED_SCOPE, CollectionRun
from amayama_scraper.persistence.db import connect
from amayama_scraper.persistence.migrations.runner import run_migrations
from amayama_scraper.persistence.repositories.checkpoint_repo import (
    get_checkpoint_entry,
    list_accepted,
    list_incomplete_runs,
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


def test_list_incomplete_runs_returns_only_matching_scope_and_null_completed_at():
    conn = _conn()  # already has run-1, scope=FIXED_SCOPE, completed_at=None
    save_collection_run(conn, CollectionRun(run_id="run-2"))  # also incomplete, same scope

    incomplete = list_incomplete_runs(conn, FIXED_SCOPE)
    run_ids = {run.run_id for run in incomplete}
    assert run_ids == {"run-1", "run-2"}


def test_list_incomplete_runs_excludes_completed_run():
    conn = _conn()
    save_collection_run(
        conn, CollectionRun(run_id="run-done", completed_at=datetime(2026, 8, 27, tzinfo=UTC))
    )

    incomplete = list_incomplete_runs(conn, FIXED_SCOPE)
    run_ids = {run.run_id for run in incomplete}
    assert "run-done" not in run_ids
    assert "run-1" in run_ids


def test_list_incomplete_runs_excludes_different_scope():
    conn = _conn()
    # CollectionRun's own __post_init__ enforces FIXED_SCOPE — a foreign-scope
    # row can only reach the table via direct SQL, which is exactly the case
    # list_incomplete_runs() must still filter out correctly (data-model.md §7).
    conn.execute(
        "INSERT INTO collection_run (run_id, scope, started_at, resumed_at, completed_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("run-other-scope", "AMAYAMA:VOLKSWAGEN:OTHER-MODEL:AMA-BR", None, None, None),
    )

    incomplete = list_incomplete_runs(conn, FIXED_SCOPE)
    run_ids = {run.run_id for run in incomplete}
    assert "run-other-scope" not in run_ids
    assert "run-1" in run_ids


def test_list_incomplete_runs_empty_when_none_exist():
    conn = connect(":memory:")
    run_migrations(conn)
    assert list_incomplete_runs(conn, FIXED_SCOPE) == []


def test_attempt_count_increments_across_repeated_start_attempt_events():
    """T051 (002) — attempt_count já existente serve como auditoria combinada
    de tentativas (transporte + validação), sem contador paralelo (research.md
    §10)."""
    from amayama_scraper.checkpoint.checkpoint_entry import CheckpointEvent
    from amayama_scraper.checkpoint.upsert import upsert_checkpoint

    conn = _conn()
    kwargs = dict(run_id="run-1", spec_key="spec-1", category_slug="engine", group_id="1")

    first = upsert_checkpoint(conn, event=CheckpointEvent.START_ATTEMPT, **kwargs)
    assert first.attempt_count == 1
    upsert_checkpoint(conn, event=CheckpointEvent.REJECT, evidence={"outcome": "INVALID"}, **kwargs)

    second = upsert_checkpoint(conn, event=CheckpointEvent.START_ATTEMPT, **kwargs)
    assert second.attempt_count == 2
    upsert_checkpoint(conn, event=CheckpointEvent.REJECT, evidence={"outcome": "INVALID"}, **kwargs)

    third = upsert_checkpoint(conn, event=CheckpointEvent.START_ATTEMPT, **kwargs)
    assert third.attempt_count == 3
