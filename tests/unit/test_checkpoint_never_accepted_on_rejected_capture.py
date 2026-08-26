"""T202 — captura CHALLENGE/TRANSLATION/INVALID/INCOMPLETE nunca produz ACCEPTED."""

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
    return conn


def test_rejected_capture_marks_checkpoint_rejected_not_accepted():
    conn = _conn()
    kwargs = dict(run_id="run-1", spec_key="spec-1", category_slug="engine", group_id="1")

    upsert_checkpoint(conn, event=CheckpointEvent.START_ATTEMPT, **kwargs)
    entry = upsert_checkpoint(
        conn, event=CheckpointEvent.REJECT, evidence={"outcome": "CHALLENGE"}, **kwargs
    )

    assert entry.status == CheckpointStatus.REJECTED
    assert entry.status != CheckpointStatus.ACCEPTED


def test_never_transitioned_stays_pending_not_accepted():
    conn = _conn()
    from amayama_scraper.persistence.repositories.checkpoint_repo import get_checkpoint_entry

    entry = get_checkpoint_entry(conn, "run-1", "spec-1", "engine", "1")
    assert entry is None  # never attempted — nothing to accidentally mark ACCEPTED
