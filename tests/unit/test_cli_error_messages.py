"""T100 — erro de uso claro para --resume + --new-run simultâneos, e para
--resume <run_id inexistente>, sem stack trace bruto (contracts/
orchestration-contract.md §4)."""

from __future__ import annotations

from pathlib import Path

import pytest

from amayama_scraper.cli.main import main
from amayama_scraper.cli.options import parse_args


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
