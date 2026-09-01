"""T200 — upsert_checkpoint(): transição PENDING → IN_PROGRESS → ACCEPTED."""

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


def _kwargs(**overrides: object) -> dict[str, object]:
    defaults: dict[str, object] = dict(
        run_id="run-1", spec_key="spec-1", category_slug="engine", group_id="1"
    )
    defaults.update(overrides)
    return defaults


def test_pending_to_in_progress_to_accepted():
    conn = _conn()
    entry = upsert_checkpoint(conn, event=CheckpointEvent.START_ATTEMPT, **_kwargs())
    assert entry.status == CheckpointStatus.IN_PROGRESS
    assert entry.attempt_count == 1

    entry = upsert_checkpoint(
        conn, event=CheckpointEvent.ACCEPT, raw_capture_id="cap-1", **_kwargs()
    )
    assert entry.status == CheckpointStatus.ACCEPTED
    assert entry.raw_capture_id == "cap-1"
    assert entry.completed_at is not None


def test_rejected_can_transition_back_to_in_progress_via_start_attempt():
    """T047 (002) — regressão/confirmação, não nova funcionalidade: a máquina
    de estados já existente de 001 já permite REJECTED -> IN_PROGRESS via
    START_ATTEMPT (checkpoint/checkpoint_entry.py::transition()). Isso é o
    que torna DEC-006 (retry manual de unidades REQUIRES_EXPLICIT_RETRY)
    implementável sem qualquer nova transição de estado (research.md §9)."""
    conn = _conn()
    upsert_checkpoint(conn, event=CheckpointEvent.START_ATTEMPT, **_kwargs())
    rejected = upsert_checkpoint(
        conn, event=CheckpointEvent.REJECT, evidence={"outcome": "INVALID"}, **_kwargs()
    )
    assert rejected.status == CheckpointStatus.REJECTED

    retried = upsert_checkpoint(conn, event=CheckpointEvent.START_ATTEMPT, **_kwargs())
    assert retried.status == CheckpointStatus.IN_PROGRESS
    assert retried.attempt_count == 2
