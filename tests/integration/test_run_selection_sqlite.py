"""T040 — select_run() contra SQLite real (plan.md "Modelo de run/resume").

Reproduz os cenários de tests/unit/test_run_selection.py agora usando os
repositórios reais (checkpoint_repo.list_incomplete_runs/get_collection_run/
save_collection_run), confirmando que a função pura se comporta
identicamente sobre persistência de verdade.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from functools import partial

import pytest

from amayama_scraper.checkpoint.collection_run import FIXED_SCOPE, CollectionRun
from amayama_scraper.orchestration.run_selection import (
    AmbiguousResumeError,
    IncompatibleResumeRunError,
    select_run,
)
from amayama_scraper.persistence.db import connect
from amayama_scraper.persistence.migrations.runner import run_migrations
from amayama_scraper.persistence.repositories.checkpoint_repo import (
    get_collection_run,
    list_incomplete_runs,
    save_collection_run,
)

_NOW = datetime(2026, 8, 28, tzinfo=UTC)


def _select(conn, **overrides: object):
    defaults: dict[str, object] = dict(
        resume_run_id=None,
        new_run=False,
        scope=FIXED_SCOPE,
        now=_NOW,
        run_id_factory=lambda: str(uuid.uuid4()),
        get_collection_run=partial(get_collection_run, conn),
        list_incomplete_runs=partial(list_incomplete_runs, conn),
        save_collection_run=partial(save_collection_run, conn),
    )
    defaults.update(overrides)
    return select_run(**defaults)  # type: ignore[arg-type]


def test_zero_incomplete_runs_creates_and_persists_new_run() -> None:
    conn = connect(":memory:")
    run_migrations(conn)

    result = _select(conn)

    assert result.created_new is True
    assert get_collection_run(conn, result.run.run_id) is not None


def test_exactly_one_incomplete_run_resumes_without_new_row() -> None:
    conn = connect(":memory:")
    run_migrations(conn)
    save_collection_run(conn, CollectionRun(run_id="run-1", started_at=_NOW))

    result = _select(conn)

    assert result.created_new is False
    assert result.run.run_id == "run-1"
    assert len(list_incomplete_runs(conn, FIXED_SCOPE)) == 1


def test_two_incomplete_runs_raise_ambiguous_and_touch_nothing() -> None:
    conn = connect(":memory:")
    run_migrations(conn)
    save_collection_run(conn, CollectionRun(run_id="run-a", started_at=_NOW))
    save_collection_run(conn, CollectionRun(run_id="run-b", started_at=_NOW))

    with pytest.raises(AmbiguousResumeError):
        _select(conn)

    # nothing new was created as a side effect of the ambiguity
    assert len(list_incomplete_runs(conn, FIXED_SCOPE)) == 2


def test_explicit_resume_of_completed_run_is_rejected() -> None:
    conn = connect(":memory:")
    run_migrations(conn)
    save_collection_run(conn, CollectionRun(run_id="run-done", started_at=_NOW, completed_at=_NOW))

    with pytest.raises(IncompatibleResumeRunError):
        _select(conn, resume_run_id="run-done")


def test_new_run_creates_independently_of_existing_incomplete() -> None:
    conn = connect(":memory:")
    run_migrations(conn)
    save_collection_run(conn, CollectionRun(run_id="run-1", started_at=_NOW))

    result = _select(conn, new_run=True)

    assert result.created_new is True
    assert result.run.run_id != "run-1"
    assert len(list_incomplete_runs(conn, FIXED_SCOPE)) == 2
