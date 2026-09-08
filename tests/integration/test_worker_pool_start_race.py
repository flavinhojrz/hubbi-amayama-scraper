"""005 hardening (post-review, 2ª rodada) — HIGH: race entre `Process.start()`
e o registro do filho na lista monitorada por `run_pool()`.

Antes da correção: `handle.start(); workers.append(handle)` deixava uma
janela em que um `KeyboardInterrupt` durante/logo após `start()` faria o
filho real existir sem nunca entrar na lista que o `finally` usa para
join()/terminate() — órfão. Depois: `workers.append(handle); handle.start()`
— o handle sempre está registrado ANTES de `start()` ser chamado."""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest
from tests.support import AMAROK_CONTEXT
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


class _InterruptingStartHandle:
    """Duplo de `_ProcessHandle` cujo `start()` efetivamente inicia o filho
    REAL (uma thread viva rodando `target`) e SÓ DEPOIS levanta
    `KeyboardInterrupt` — reproduz exatamente o cenário do achado: o
    processo/thread real já existe no instante em que a exceção ocorre
    dentro de `start()`."""

    def __init__(self, target, args) -> None:  # noqa: ANN001
        self._thread = threading.Thread(target=self._run, args=())
        self._target = target
        self._args = args
        self._exception: BaseException | None = None
        self.exitcode: int | None = None

    def _run(self) -> None:
        try:
            self._target(*self._args)
        except BaseException as exc:  # noqa: BLE001
            self._exception = exc

    def start(self) -> None:
        self._thread.start()  # o filho real "nasce" aqui...
        raise KeyboardInterrupt()  # ...e SÓ ENTÃO start() é interrompido

    def join(self, timeout: float | None = None) -> None:
        self._thread.join(timeout)
        if not self._thread.is_alive():
            self.exitcode = 1 if self._exception is not None else 0

    def is_alive(self) -> bool:
        return self._thread.is_alive()

    def terminate(self) -> None:
        pass

    @property
    def pid(self) -> int | None:
        return self._thread.ident


class _FailingStartHandle:
    """Duplo cujo `start()` falha ANTES de qualquer criação efetiva do
    filho (`pid` permanece `None` para sempre) — simula, por exemplo,
    `multiprocessing.Process.start()` levantando `OSError` por falta de
    recursos do SO. `join()`/`is_alive()`/`terminate()` levantam
    `AssertionError` se chamados — provam que `run_pool()` nunca os invoca
    num handle que nunca chegou a iniciar de fato."""

    def __init__(self) -> None:
        self.exitcode: int | None = None

    def start(self) -> None:
        raise OSError("simulated: could not create child process")

    def join(self, timeout: float | None = None) -> None:
        raise AssertionError("join() must never be called on a handle that never started")

    def is_alive(self) -> bool:
        raise AssertionError("is_alive() must never be called on a handle that never started")

    def terminate(self) -> None:
        raise AssertionError("terminate() must never be called on a handle that never started")

    @property
    def pid(self) -> int | None:
        return None


def _run_pool_kwargs(tmp_path: Path, *, worker_target, process_factory, stop_event):  # noqa: ANN001
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

    return dict(
        transport=orchestrator_transport,
        conn=conn,
        blob_store=blob_store,
        capture_repo=capture_repo,
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
        sleep=lambda _s: None,
        terminate_timeout=5.0,
        on_event=lambda *a, **kw: None,
    )


def test_keyboard_interrupt_exactly_during_start_still_joins_the_real_child(
    tmp_path: Path,
) -> None:
    worker_saw_stop = threading.Event()

    def worker_target(worker_args: WorkerProcessArgs, stop_event: threading.Event) -> None:
        # simula um worker "vivo" que só encerra ao ver o sinal cooperativo.
        while not stop_event.is_set():
            time.sleep(0.005)
        worker_saw_stop.set()

    def process_factory(target, worker_args, stop_event):  # noqa: ANN001, ANN201
        return _InterruptingStartHandle(target, (worker_args, stop_event))

    stop_event = threading.Event()
    kwargs = _run_pool_kwargs(
        tmp_path,
        worker_target=worker_target,
        process_factory=process_factory,
        stop_event=stop_event,
    )

    with pytest.raises(KeyboardInterrupt):
        run_pool(
            kwargs.pop("transport"),
            kwargs.pop("conn"),
            kwargs.pop("blob_store"),
            kwargs.pop("capture_repo"),
            **kwargs,
        )

    # o KeyboardInterrupt de dentro de start() continua sendo propagado
    # (pytest.raises acima já prova isso) — E o cleanup, mesmo assim, aguarda
    # o filho REAL que já tinha nascido: nunca fica órfão.
    assert stop_event.is_set()
    assert worker_saw_stop.is_set()


def test_start_failure_before_real_child_creation_never_calls_join_or_terminate(
    tmp_path: Path,
) -> None:
    def worker_target(worker_args, stop_event) -> None:  # noqa: ANN001
        pytest.fail("worker_target must never run — start() failed before any child existed")

    def process_factory(target, worker_args, stop_event):  # noqa: ANN001, ANN201
        return _FailingStartHandle()

    stop_event = threading.Event()
    kwargs = _run_pool_kwargs(
        tmp_path,
        worker_target=worker_target,
        process_factory=process_factory,
        stop_event=stop_event,
    )

    with pytest.raises(OSError, match="simulated: could not create child process"):
        run_pool(
            kwargs.pop("transport"),
            kwargs.pop("conn"),
            kwargs.pop("blob_store"),
            kwargs.pop("capture_repo"),
            **kwargs,
        )

    # Se o cleanup tivesse chamado join()/is_alive()/terminate() no handle
    # que nunca iniciou, _FailingStartHandle teria levantado AssertionError
    # ali dentro — o que teria mascarado/substituído o OSError original
    # (exceção levantada dentro de um `finally` sobrepõe a que já estava
    # propagando). `pytest.raises(OSError, match=...)` acima já prova que
    # isso NÃO aconteceu.
    assert stop_event.is_set()  # ainda assim sinalizado, mesmo sem nenhum filho real
