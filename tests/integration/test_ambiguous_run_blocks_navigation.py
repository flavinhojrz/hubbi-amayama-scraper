"""T110 — run ambíguo: duas execuções incompletas do mesmo escopo; uma
terceira invocação sem --resume/--new-run falha antes de qualquer
navegação (DEC-005, SC-010)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from amayama_scraper.checkpoint.collection_run import CollectionRun
from amayama_scraper.cli.main import main
from amayama_scraper.persistence.db import connect
from amayama_scraper.persistence.migrations.runner import run_migrations
from amayama_scraper.persistence.repositories.checkpoint_repo import save_collection_run


def test_ambiguous_incomplete_runs_reject_before_any_navigation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = str(tmp_path / "amayama.db")
    raw_root = tmp_path / "raw"

    conn = connect(db_path)
    run_migrations(conn)
    now = datetime(2026, 8, 28, tzinfo=UTC)
    save_collection_run(conn, CollectionRun(run_id="run-a", started_at=now))
    save_collection_run(conn, CollectionRun(run_id="run-b", started_at=now))
    conn.close()

    def _fail_if_instantiated(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("transport must never be instantiated on ambiguous run selection")

    monkeypatch.setattr("amayama_scraper.cli.main.ChromeCdpTransport", _fail_if_instantiated)

    exit_code = main(["run", "--db-path", db_path, "--raw-root", str(raw_root)])

    assert exit_code == 2
    captured = capsys.readouterr()
    assert "run-a" in captured.err
    assert "run-b" in captured.err
