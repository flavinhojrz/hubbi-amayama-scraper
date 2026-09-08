"""005 hardening (post-review) — BLOCKER 3: `run_pool()` faz shutdown
determinístico em `KeyboardInterrupt` — sinaliza `stop_event`, aguarda os
filhos, `terminate()` os que sobrarem, sempre `join()` todos antes de
propagar a exceção. Nenhum worker órfão após `run_pool()` retornar/levantar."""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest
from tests.support import AMAROK_CONTEXT, ThreadProcessHandle
from tests.unit.fakes import FakeBrowserTransport

from amayama_scraper.checkpoint.collection_run import CollectionRun
from amayama_scraper.domain.discovery import build_market_index_url
from amayama_scraper.orchestration.collection_driver import OperationalFilters
from amayama_scraper.orchestration.worker_pool import WorkerPoolConfig, WorkerProcessArgs, run_pool
from amayama_scraper.persistence.adapters.filesystem_raw_blob_store import FilesystemRawBlobStore
from amayama_scraper.persistence.adapters.sqlite_raw_capture_repository import (
    SqliteRawCaptureRepository,
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


def test_run_pool_shuts_down_workers_deterministically_on_keyboard_interrupt(
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

    worker_saw_stop = threading.Event()

    def worker_target(worker_args: WorkerProcessArgs, stop_event: threading.Event) -> None:
        # Simula um worker "ocupado" (ex.: no meio de um processamento
        # longo) que só encerra ao ver o sinal cooperativo — nunca
        # espontaneamente, nunca preso para sempre.
        while not stop_event.is_set():
            time.sleep(0.005)
        worker_saw_stop.set()

    def process_factory(target, worker_args, stop_event):  # noqa: ANN001, ANN201
        return ThreadProcessHandle(target, (worker_args, stop_event))

    def interrupting_sleep(_seconds: float) -> None:
        raise KeyboardInterrupt()

    stop_event = threading.Event()
    with pytest.raises(KeyboardInterrupt):
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
            stop_event=stop_event,
            sleep=interrupting_sleep,
            terminate_timeout=5.0,
            on_event=lambda *a, **kw: None,
        )

    # stop_event foi sinalizado (encerramento cooperativo) e o worker
    # efetivamente o observou e retornou — run_pool() só propaga o
    # KeyboardInterrupt DEPOIS de aguardar/join() o worker (nunca antes).
    assert stop_event.is_set()
    assert worker_saw_stop.is_set()
