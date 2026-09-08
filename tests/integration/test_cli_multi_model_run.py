"""CLI de coleta reutilizável para outros modelos Volkswagen (evolução
multi-modelo do 002): --manufacturer/--vehicle-model/--market substituem os
antigos FIXED_SCOPE/MARKET_INDEX_URL fixos na Amarok."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from tests.support import AMAROK_CONTEXT, GOL_CONTEXT
from tests.unit.fakes import FakeBrowserTransport

from amayama_scraper.checkpoint.collection_run import FIXED_SCOPE
from amayama_scraper.cli.main import main
from amayama_scraper.domain.discovery import build_market_index_url
from amayama_scraper.persistence.db import connect
from amayama_scraper.persistence.repositories.checkpoint_repo import list_incomplete_runs
from amayama_scraper.persistence.repositories.spec_registry_repo import list_by_scope
from amayama_scraper.transport.port import BrowserCapture

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
MARKET_INDEX_HTML = (FIXTURES / "market_index" / "same_model_code_diff_catalog.html").read_text(
    encoding="utf-8"
)


def _capture(html: str, url: str) -> BrowserCapture:
    return BrowserCapture(page_source=html, effective_url=url, captured_at=datetime.now(UTC))


def test_cli_run_for_another_vehicle_model_uses_its_own_scope_and_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = str(tmp_path / "amayama.db")
    raw_root = tmp_path / "raw"

    gol_url = build_market_index_url(GOL_CONTEXT)
    fake = FakeBrowserTransport()
    fake.queue_navigate(_capture(MARKET_INDEX_HTML, gol_url))
    monkeypatch.setattr("amayama_scraper.cli.main.ChromeCdpTransport", lambda **_kw: fake)

    exit_code = main(
        [
            "run",
            "--vehicle-model",
            "GOL",
            "--limit-specs",
            "0",
            "--db-path",
            db_path,
            "--raw-root",
            str(raw_root),
        ]
    )

    assert exit_code == 0
    assert fake.navigate_calls == [gol_url]

    conn = connect(db_path)
    gol_scope = GOL_CONTEXT.scope()
    assert gol_scope != FIXED_SCOPE
    assert len(list_incomplete_runs(conn, gol_scope)) == 1
    # nenhum run/scope foi criado por engano sob o escopo default da Amarok
    assert list_incomplete_runs(conn, FIXED_SCOPE) == []

    gol_specs = list_by_scope(conn, manufacturer="VOLKSWAGEN", vehicle_model="GOL", market="AMA-BR")
    assert len(gol_specs) == 2
    amarok_leak = list_by_scope(
        conn, manufacturer="VOLKSWAGEN", vehicle_model="AMAROK", market="AMA-BR"
    )
    assert amarok_leak == []


def test_cli_run_with_defaults_still_uses_the_historical_amarok_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = str(tmp_path / "amayama.db")
    raw_root = tmp_path / "raw"

    amarok_url = build_market_index_url(AMAROK_CONTEXT)
    fake = FakeBrowserTransport()
    fake.queue_navigate(_capture(MARKET_INDEX_HTML, amarok_url))
    monkeypatch.setattr("amayama_scraper.cli.main.ChromeCdpTransport", lambda **_kw: fake)

    exit_code = main(
        [
            "run",
            "--limit-specs",
            "0",
            "--db-path",
            db_path,
            "--raw-root",
            str(raw_root),
        ]
    )

    assert exit_code == 0
    assert fake.navigate_calls == [amarok_url]
    conn = connect(db_path)
    assert len(list_incomplete_runs(conn, FIXED_SCOPE)) == 1
