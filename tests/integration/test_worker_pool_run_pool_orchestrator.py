"""Cobertura direta de `orchestration/worker_pool.py::run_pool()` — o
orquestrador real chamado por `cli/main.py` para `--workers N > 1`
(complementa T511/T513-T515, que testam `next_claimable_spec()`/
`run_worker_loop()` isoladamente, mas não `run_pool()` em si).

`process_factory`/`worker_target` são duplos injetados (threads rodando
`run_worker_loop()` com `FakeBrowserTransport` própria) — prova a
orquestração real (Nível A sequencial -> spawn -> loop de métricas -> join
-> `_maybe_mark_run_completed()` uma única vez) sem exigir
`multiprocessing`/Chrome real (mesmo padrão de teste já usado em
test_worker_pool_no_double_claim.py/test_worker_pool_context_isolation.py)."""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from pathlib import Path

from tests.support import AMAROK_CONTEXT, ThreadProcessHandle
from tests.unit.fakes import FakeBrowserTransport

from amayama_scraper.checkpoint.collection_run import CollectionRun
from amayama_scraper.domain.discovery import build_market_index_url
from amayama_scraper.orchestration.collection_driver import OperationalFilters
from amayama_scraper.orchestration.worker_pool import (
    WorkerPoolConfig,
    WorkerProcessArgs,
    run_pool,
    run_worker_loop,
)
from amayama_scraper.parsing.market_index import parse_market_spec_index
from amayama_scraper.persistence.adapters.filesystem_raw_blob_store import FilesystemRawBlobStore
from amayama_scraper.persistence.adapters.sqlite_raw_capture_repository import (
    SqliteRawCaptureRepository,
)
from amayama_scraper.persistence.db import connect
from amayama_scraper.persistence.migrations.runner import run_migrations
from amayama_scraper.persistence.repositories.checkpoint_repo import (
    get_collection_run,
    save_collection_run,
)
from amayama_scraper.persistence.repositories.current_state_repo import get_current_state
from amayama_scraper.persistence.repositories.spec_registry_repo import list_by_scope
from amayama_scraper.transport.port import BrowserCapture

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
# 1 spec entry — permite provar conclusão de run com um único worker.
MARKET_INDEX_HTML = (FIXTURES / "market_index" / "open_ended_period.html").read_text(
    encoding="utf-8"
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


def _spec_url() -> str:
    result = parse_market_spec_index(MARKET_INDEX_HTML, source_capture_id="cap-x")
    assert result.entries
    return result.entries[0].source_url


def test_run_pool_orchestrates_market_index_then_workers_then_completes_once(
    tmp_path: Path,
) -> None:
    db_path = str(tmp_path / "pool.db")
    raw_root = tmp_path / "blobs"
    conn = connect(db_path)
    run_migrations(conn)
    save_collection_run(conn, CollectionRun(run_id="run-1", scope=AMAROK_CONTEXT.scope()))
    blob_store = FilesystemRawBlobStore(raw_root, conn)
    capture_repo = SqliteRawCaptureRepository(conn)

    market_index_url = build_market_index_url(AMAROK_CONTEXT)
    orchestrator_transport = FakeBrowserTransport()
    orchestrator_transport.queue_navigate(_capture(MARKET_INDEX_HTML, market_index_url))

    spec_url = _spec_url()

    def worker_target(worker_args: WorkerProcessArgs, stop_event: threading.Event) -> None:
        worker_conn = connect(worker_args.db_path)
        worker_blob_store = FilesystemRawBlobStore(Path(worker_args.raw_root), worker_conn)
        worker_capture_repo = SqliteRawCaptureRepository(worker_conn)
        transport = FakeBrowserTransport()
        transport.queue_navigate(_capture(MANIFEST_HTML, spec_url))
        transport.queue_navigate(_capture(GROUP_HTML, "https://x/front-axle-steering/407"))
        run_worker_loop(
            transport,
            worker_conn,
            worker_blob_store,
            worker_capture_repo,
            run_id=worker_args.run_id,
            context=worker_args.context,
            worker_id=f"worker-{worker_args.worker_index}",
            filters=worker_args.filters,
            pool_config=worker_args.pool_config,
            pool_session_id=worker_args.pool_session_id,
            sleep=lambda _s: None,
            stop_event=stop_event,
        )
        worker_conn.close()

    def process_factory(target, worker_args, stop_event):  # noqa: ANN001, ANN201
        return ThreadProcessHandle(target, (worker_args, stop_event))

    events: list[str] = []
    run_pool(
        orchestrator_transport,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        context=AMAROK_CONTEXT,
        filters=OperationalFilters(),
        pool_config=WorkerPoolConfig(workers=1, metrics_interval_seconds=0.01),
        db_path=db_path,
        raw_root=str(raw_root),
        cdp_host="127.0.0.1",
        cdp_ports=[9222],
        worker_target=worker_target,
        process_factory=process_factory,
        stop_event=threading.Event(),
        sleep=lambda _s: None,
        on_event=lambda event, **kw: events.append(event),
    )

    assert "RUN_STARTED" in events
    assert "RUN_SUMMARY" in events

    specs = list_by_scope(conn, manufacturer="VOLKSWAGEN", vehicle_model="AMAROK", market="AMA-BR")
    assert len(specs) == 1
    assert get_current_state(conn, specs[0].stable_key()) is not None

    run = get_collection_run(conn, "run-1")
    assert run is not None and run.completed_at is not None  # _maybe_mark_run_completed rodou
