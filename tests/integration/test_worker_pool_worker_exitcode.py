"""005 hardening (post-review) — HIGH 4: após o `join()` final, `run_pool()`
verifica o `exitcode` de cada worker — um worker filho que falha
inesperadamente nunca vira sucesso silencioso; `WorkerProcessFailedError`
identifica worker/porta/exitcode."""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from pathlib import Path

import pytest
from tests.support import AMAROK_CONTEXT, ThreadProcessHandle
from tests.unit.fakes import FakeBrowserTransport

from amayama_scraper.checkpoint.collection_run import CollectionRun
from amayama_scraper.domain.discovery import build_market_index_url
from amayama_scraper.orchestration.collection_driver import OperationalFilters
from amayama_scraper.orchestration.worker_pool import (
    WorkerPoolConfig,
    WorkerProcessArgs,
    WorkerProcessFailedError,
    run_pool,
)
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


def test_worker_process_failure_never_reports_pool_success(tmp_path: Path) -> None:
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

    def worker_target(worker_args: WorkerProcessArgs, stop_event) -> None:  # noqa: ANN001
        raise RuntimeError("simulated unexpected worker crash")

    def process_factory(target, worker_args, stop_event):  # noqa: ANN001, ANN201
        return ThreadProcessHandle(target, (worker_args, stop_event))

    with pytest.raises(WorkerProcessFailedError) as exc_info:
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
            on_event=lambda *a, **kw: None,
        )

    failures = exc_info.value.failures
    assert len(failures) == 1
    worker_index, cdp_port, exitcode = failures[0]
    assert worker_index == 0
    assert cdp_port == 9222
    assert exitcode == 1
