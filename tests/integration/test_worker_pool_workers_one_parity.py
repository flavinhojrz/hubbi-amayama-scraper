"""T522 — SC-001/US1: `--workers 1` (novo branch de cli/main.py, 005) produz
exatamente os mesmos eventos/checkpoints que o pipeline pré-005 (omitir
`--workers`, que assume o default `1`) — mesma cena, dois bancos/`tmp_path`
distintos, comparando a sequência de eventos (normalizada por `run_id`/
`timestamp`, que variam por natureza) e o estado final do banco."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest
from tests.unit.fakes import FakeBrowserTransport

from amayama_scraper.cli.main import main
from amayama_scraper.persistence.db import connect
from amayama_scraper.persistence.repositories.current_state_repo import get_current_state
from amayama_scraper.persistence.repositories.spec_registry_repo import (
    find_by_model_code_and_catalog_id,
)
from amayama_scraper.transport.port import BrowserCapture

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
MARKET_INDEX_HTML = (FIXTURES / "market_index" / "same_model_code_diff_catalog.html").read_text(
    encoding="utf-8"
)
MARKET_INDEX_URL = (
    "https://www.amayama.com/en/genuine-catalogs/epc/volkswagen-overall/amarok/ama-br"
)
_SPEC_URL = (
    "https://www.amayama.com/en/genuine-catalogs/epc/volkswagen-overall/amarok/ama-br/s7bc8a-62184"
)

MANIFEST_HTML = """
<html><body>
  <div class="epcVariation__details">
    <div class="epcVariation__filters">
      <div class="epcVariation__schemaGroups">
        <a class="epcVariation__schemaGroup active" data-id="" href="https://x#">All</a>
        <a class="epcVariation__schemaGroup" data-id="4" href="https://x/front-axle-steering">FA</a>
      </div>
    </div>
    <div class="epcVariation__schemas">
      <div class="epcVariation__schema" data-id="407">
        <div class="epcVariation__schema-name"><a href="https://x/front-axle-steering/407">407</a></div>
      </div>
    </div>
  </div>
</body></html>
"""

GROUP_HTML = """
<html><body><div class="epcVariation__details"><div class="epcSchema__schemas">
  <div class="epcSchema__schema" data-id="SCH-1"><table class="entriesTable">
    <tr data-key="A01"><td class="entriesTable__number">1K0407151</td>
    <td class="entriesTable__description">Control arm</td>
    <td class="entriesTable__period">08.2010-12.2015</td>
    <td class="entriesTable__required">1</td></tr>
  </table></div>
</div></div></body></html>
"""


def _capture(html: str, url: str) -> BrowserCapture:
    return BrowserCapture(page_source=html, effective_url=url, captured_at=datetime.now(UTC))


def _run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, workers_args: list[str]
) -> tuple[int, str, str]:
    db_path = str(tmp_path / "amayama.db")
    raw_root = tmp_path / "raw"

    fake = FakeBrowserTransport()
    fake.queue_navigate(_capture(MARKET_INDEX_HTML, MARKET_INDEX_URL))
    fake.queue_navigate(_capture(MANIFEST_HTML, _SPEC_URL))
    fake.queue_navigate(_capture(GROUP_HTML, "https://x/front-axle-steering/407"))
    monkeypatch.setattr("amayama_scraper.cli.main.ChromeCdpTransport", lambda **_kw: fake)

    exit_code = main(
        [
            "run",
            *workers_args,
            "--limit-specs",
            "1",
            "--limit-groups",
            "2",
            "--db-path",
            db_path,
            "--raw-root",
            str(raw_root),
        ]
    )
    return exit_code, db_path, ""


def _normalized_events(stdout: str) -> list[dict]:
    """Cada linha JSON, com `run_id`/`timestamp` removidos (variam por
    natureza entre invocações — não fazem parte do comportamento a
    comparar)."""
    events = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        payload = json.loads(line)
        payload.pop("run_id", None)
        payload.pop("timestamp", None)
        events.append(payload)
    return events


def _normalized_summary(stdout: str) -> str:
    for line in stdout.splitlines():
        if line.startswith("SUMMARY"):
            return re.sub(r"run_id=\S+", "run_id=<X>", line)
    return ""


def test_no_workers_flag_and_explicit_workers_one_produce_identical_events(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    legacy_dir = tmp_path / "legacy"
    legacy_dir.mkdir()
    exit_code_legacy, db_path_legacy, _ = _run(legacy_dir, monkeypatch, workers_args=[])
    captured_legacy = capsys.readouterr()

    explicit_dir = tmp_path / "explicit"
    explicit_dir.mkdir()
    exit_code_explicit, db_path_explicit, _ = _run(
        explicit_dir, monkeypatch, workers_args=["--workers", "1"]
    )
    captured_explicit = capsys.readouterr()

    assert exit_code_legacy == exit_code_explicit == 0
    assert _normalized_events(captured_legacy.out) == _normalized_events(captured_explicit.out)
    assert _normalized_summary(captured_legacy.out) == _normalized_summary(captured_explicit.out)
    assert captured_legacy.err == captured_explicit.err == ""

    conn_legacy = connect(db_path_legacy)
    conn_explicit = connect(db_path_explicit)
    key_legacy = find_by_model_code_and_catalog_id(conn_legacy, "S7BC8A", "62184")[0].stable_key()
    key_explicit = find_by_model_code_and_catalog_id(conn_explicit, "S7BC8A", "62184")[
        0
    ].stable_key()
    assert key_legacy == key_explicit  # mesma identidade (determinística, mesmo input)
    assert get_current_state(conn_legacy, key_legacy) is not None
    assert get_current_state(conn_explicit, key_explicit) is not None
