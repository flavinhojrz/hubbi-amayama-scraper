"""T101/T107 — `amayama-scraper run --limit-specs 1 --limit-groups 2` ponta a
ponta via CLI, com ChromeCdpTransport substituído por FakeBrowserTransport
(injeção de dependência no ponto de composição, exclusivamente para este
teste) — confirma que exatamente os limites pedidos são respeitados e
persistidos, e que a saída de terminal contém os campos exigidos por FR-027."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from tests.unit.fakes import FakeBrowserTransport

from amayama_scraper.checkpoint.collection_run import FIXED_SCOPE
from amayama_scraper.cli.main import main
from amayama_scraper.persistence.db import connect
from amayama_scraper.persistence.repositories.checkpoint_repo import list_incomplete_runs
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


def test_limited_run_via_cli_persists_exactly_what_was_requested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
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

    assert exit_code == 0
    conn = connect(db_path)
    key = find_by_model_code_and_catalog_id(conn, "S7BC8A", "62184")[0].stable_key()
    from amayama_scraper.persistence.repositories.current_state_repo import get_current_state

    assert get_current_state(conn, key) is not None  # reached VALID within the CLI-driven run

    # Exactly one CollectionRun exists for this scope after this invocation.
    # It remains "incomplete" (completed_at is never set by this MVP's driver
    # — no run-level completion concept is defined by spec.md/plan.md/tasks.md,
    # only spec-level VALID/STALE) so that a later invocation's default
    # auto-resume (DEC-005) picks it up instead of spuriously creating a new
    # one — what this assertion actually guards is that this single CLI call
    # created exactly one run, never two.
    runs = list_incomplete_runs(conn, FIXED_SCOPE)
    assert len(runs) == 1

    # FR-027: RUN/SPEC/GROUP/progresso/ACCEPTED/.../resumo final — emitidos
    # como JSON lines (progress_reporter.py, research.md §15) + uma linha
    # de resumo final legível.
    captured = capsys.readouterr()
    assert '"event": "RUN_STARTED"' in captured.out
    assert '"event": "SPEC_STARTED"' in captured.out
    assert '"event": "GROUP_ACCEPTED"' in captured.out
    assert "SUMMARY" in captured.out
    assert "ACCEPTED=1" in captured.out
