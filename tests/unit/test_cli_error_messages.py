"""T100 — erro de uso claro para --resume + --new-run simultâneos, e para
--resume <run_id inexistente>, sem stack trace bruto (contracts/
orchestration-contract.md §4)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from amayama_scraper.cli.main import main
from amayama_scraper.cli.options import parse_args
from amayama_scraper.persistence.db import connect
from amayama_scraper.persistence.migrations.runner import run_migrations


def test_resume_and_new_run_together_is_a_usage_error_before_any_orchestration() -> None:
    with pytest.raises(SystemExit) as exc_info:
        parse_args(["run", "--resume", "abc", "--new-run"])
    assert exc_info.value.code == 2  # argparse's standard usage-error exit code


def test_resume_of_nonexistent_run_returns_clear_error_exit_code(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = str(tmp_path / "amayama.db")
    raw_root = tmp_path / "raw"

    exit_code = main(
        ["run", "--resume", "does-not-exist", "--db-path", db_path, "--raw-root", str(raw_root)]
    )

    assert exit_code == 2
    captured = capsys.readouterr()
    assert "does-not-exist" in captured.err
    assert "Traceback" not in captured.err  # no raw stack trace exposed to the operator


def _seed_corrupted_scope_run(db_path: str, run_id: str) -> None:
    """Escreve uma linha de CollectionRun com scope malformado diretamente
    via SQL — só possível externamente a este projeto (CollectionRun.
    __post_init__ nunca aceitaria isso em Python, 004)."""
    conn = connect(db_path)
    run_migrations(conn)
    conn.execute(
        "INSERT INTO collection_run (run_id, scope, started_at) VALUES (?, ?, ?)",
        (run_id, "NOT-A-VALID-SCOPE", datetime.now(UTC).isoformat()),
    )
    conn.close()


def _no_data_written(db_path: str) -> bool:
    conn = connect(db_path)
    tables = ("raw_capture", "spec_registry", "checkpoint_entry", "spec_snapshot")
    counts = [conn.execute(f"SELECT COUNT(*) AS c FROM {t}").fetchone()["c"] for t in tables]
    conn.close()
    return all(c == 0 for c in counts)


def test_resume_of_corrupted_scope_fails_closed_in_dry_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """004, item 5: um CollectionRun.scope corrompido no banco nunca é
    tratado silenciosamente como Amarok/default — falha fechada, exit code
    documentado (5), sem traceback cru, nada escrito."""
    db_path = str(tmp_path / "amayama.db")
    _seed_corrupted_scope_run(db_path, "corrupt-run")

    exit_code = main(["run", "--dry-run", "--resume", "corrupt-run", "--db-path", db_path])

    assert exit_code == 5
    captured = capsys.readouterr()
    assert "Traceback" not in captured.err
    assert "error:" in captured.err
    assert _no_data_written(db_path)


def test_resume_of_corrupted_scope_fails_closed_in_real_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = str(tmp_path / "amayama.db")
    raw_root = tmp_path / "raw"
    _seed_corrupted_scope_run(db_path, "corrupt-run")

    exit_code = main(
        ["run", "--resume", "corrupt-run", "--db-path", db_path, "--raw-root", str(raw_root)]
    )

    assert exit_code == 5
    captured = capsys.readouterr()
    assert "Traceback" not in captured.err
    assert "error:" in captured.err
    assert _no_data_written(db_path)
