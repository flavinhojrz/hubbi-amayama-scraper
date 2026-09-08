"""cli/main.py: ChromeNotReachableError na construção do transporte produz
erro claro (exit code 3), nunca uma execução silenciosa nem stack trace
bruto (research.md §4)."""

from __future__ import annotations

from pathlib import Path

import pytest

from amayama_scraper.cli.main import main
from amayama_scraper.transport.errors import ChromeNotReachableError


def test_chrome_not_reachable_returns_clear_error_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = str(tmp_path / "amayama.db")
    raw_root = tmp_path / "raw"

    def _raise(*_args: object, **_kwargs: object):
        raise ChromeNotReachableError("http://127.0.0.1:9222/json/version unreachable")

    monkeypatch.setattr("amayama_scraper.cli.main.ChromeCdpTransport", _raise)

    exit_code = main(["run", "--db-path", db_path, "--raw-root", str(raw_root)])

    assert exit_code == 3
    captured = capsys.readouterr()
    assert "unreachable" in captured.err
    assert "Traceback" not in captured.err
