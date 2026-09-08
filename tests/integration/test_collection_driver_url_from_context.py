"""004 Blocker/HIGH item 4 — a URL do índice de mercado pertence
exclusivamente ao CollectionContext.

`run_collection_driver()` deixou de aceitar `market_index_url` como
parâmetro separado (duas fontes de verdade independentes permitiriam
navegar para a URL de um modelo enquanto processa/persiste sob o contexto
de outro). A URL é sempre derivada internamente via
`build_market_index_url(context)` — o cenário "context = GOL, URL = Amarok"
citado no achado do Codex deixou de ser apenas rejeitado: tornou-se
estruturalmente impossível de sequer construir a chamada.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from tests.support import AMAROK_CONTEXT, GOL_CONTEXT
from tests.unit.fakes import (
    FakeBrowserTransport,
    InMemoryRawBlobStore,
    InMemoryRawCaptureRepository,
)

from amayama_scraper.checkpoint.collection_run import CollectionRun
from amayama_scraper.domain.discovery import build_market_index_url
from amayama_scraper.orchestration.collection_driver import (
    OperationalFilters,
    run_collection_driver,
)
from amayama_scraper.persistence.db import connect
from amayama_scraper.persistence.migrations.runner import run_migrations
from amayama_scraper.persistence.repositories.checkpoint_repo import save_collection_run
from amayama_scraper.transport.port import BrowserCapture

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
MARKET_INDEX_HTML = (FIXTURES / "market_index" / "same_model_code_diff_catalog.html").read_text(
    encoding="utf-8"
)


def _capture(html: str, url: str) -> BrowserCapture:
    return BrowserCapture(page_source=html, effective_url=url, captured_at=datetime.now(UTC))


def _conn(tmp_path: Path):
    conn = connect(str(tmp_path / "db.sqlite3"))
    run_migrations(conn)
    return conn


def test_run_collection_driver_no_longer_accepts_a_separate_market_index_url(
    tmp_path: Path,
) -> None:
    """Prova em nível de assinatura: não é mais possível sequer construir
    uma chamada com uma URL independente do context (duas fontes de
    verdade)."""
    conn = _conn(tmp_path)
    save_collection_run(conn, CollectionRun(run_id="run-1", scope=AMAROK_CONTEXT.scope()))
    blob_store, capture_repo = InMemoryRawBlobStore(), InMemoryRawCaptureRepository()
    transport = FakeBrowserTransport()

    with pytest.raises(TypeError, match="market_index_url"):
        run_collection_driver(
            transport,
            conn,
            blob_store,
            capture_repo,
            run_id="run-1",
            market_index_url="https://www.amayama.com/en/genuine-catalogs/epc/volkswagen-overall/amarok/ama-br",  # noqa: E501
            context=AMAROK_CONTEXT,
        )


@pytest.mark.parametrize("context", [AMAROK_CONTEXT, GOL_CONTEXT])
def test_driver_always_navigates_to_the_url_derived_from_its_own_context(
    tmp_path: Path, context
) -> None:
    conn = _conn(tmp_path)
    save_collection_run(conn, CollectionRun(run_id="run-1", scope=context.scope()))
    blob_store, capture_repo = InMemoryRawBlobStore(), InMemoryRawCaptureRepository()

    expected_url = build_market_index_url(context)
    transport = FakeBrowserTransport()
    transport.queue_navigate(_capture(MARKET_INDEX_HTML, expected_url))

    run_collection_driver(
        transport,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        context=context,
        filters=OperationalFilters(limit_specs=0),
        on_event=lambda *a, **kw: None,
    )

    assert transport.navigate_calls == [expected_url]
