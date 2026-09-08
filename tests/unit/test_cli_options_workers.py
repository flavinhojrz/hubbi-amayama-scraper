"""T521 — --workers fora de [1, 4] é rejeitado antes de qualquer
navegação/DB (005 FR-001), mesmo padrão de falha fechada já usado para
--manufacturer/--vehicle-model/--market inválidos (004,
tests/unit/test_cli_error_messages.py)."""

from __future__ import annotations

from pathlib import Path

import pytest

from amayama_scraper.cli.main import main
from amayama_scraper.cli.options import parse_args
from amayama_scraper.persistence.db import connect
from amayama_scraper.persistence.migrations.runner import run_migrations


def _no_data_and_no_db_file(db_path: str) -> bool:
    if not Path(db_path).exists():
        return True
    conn = connect(db_path)
    run_migrations(conn)
    tables = ("raw_capture", "spec_registry", "checkpoint_entry", "spec_snapshot", "collection_run")
    counts = [conn.execute(f"SELECT COUNT(*) AS c FROM {t}").fetchone()["c"] for t in tables]
    conn.close()
    return all(c == 0 for c in counts)


@pytest.mark.parametrize("workers", [0, 5, -1, 100])
def test_workers_out_of_range_is_rejected_before_any_navigation_or_db(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], workers: int
) -> None:
    db_path = str(tmp_path / "amayama.db")
    raw_root = tmp_path / "raw"

    exit_code = main(
        [
            "run",
            "--workers",
            str(workers),
            "--db-path",
            db_path,
            "--raw-root",
            str(raw_root),
        ]
    )

    assert exit_code == 6
    captured = capsys.readouterr()
    assert "Traceback" not in captured.err
    assert "error:" in captured.err
    assert "--workers" in captured.err
    assert _no_data_and_no_db_file(db_path)
    assert not raw_root.exists()


@pytest.mark.parametrize("workers", [1, 2, 3, 4])
def test_workers_in_range_is_accepted_by_the_parser(workers: int) -> None:
    args = parse_args(["run", "--workers", str(workers)])
    assert args.workers == workers


def test_workers_defaults_to_one() -> None:
    args = parse_args(["run"])
    assert args.workers == 1


def test_cdp_ports_count_mismatch_is_rejected_before_any_navigation_or_db(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = str(tmp_path / "amayama.db")
    raw_root = tmp_path / "raw"

    exit_code = main(
        [
            "run",
            "--workers",
            "2",
            "--cdp-ports",
            "9222,9223,9224",  # 3 portas para 2 workers — inconsistente
            "--db-path",
            db_path,
            "--raw-root",
            str(raw_root),
        ]
    )

    assert exit_code == 6
    captured = capsys.readouterr()
    assert "Traceback" not in captured.err
    assert "--cdp-ports" in captured.err
