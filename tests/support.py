"""Constantes de CollectionContext compartilhadas pela suíte (004).

`process_capture()`/`run_collection_driver()` exigem `context` explícito
(sem default, 004 item 1) — a grande maioria dos testes existentes é
Amarok/AMA-BR (o mesmo scope default histórico), então centralizam aqui em
vez de repetir `CollectionContext(...)` em cada arquivo.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Callable

from amayama_scraper.domain.collection_context import CollectionContext

AMAROK_CONTEXT = CollectionContext(
    manufacturer="VOLKSWAGEN", vehicle_model="AMAROK", market="AMA-BR"
)
GOL_CONTEXT = CollectionContext(manufacturer="VOLKSWAGEN", vehicle_model="GOL", market="AMA-BR")


def register_spec(
    conn: sqlite3.Connection,
    spec_key: str,
    context: CollectionContext,
    *,
    model_code: str = "TESTMODEL",
    amayama_catalog_id: str = "000000",
) -> None:
    """Insere uma SpecIdentity mínima em `spec_registry` sob o `stable_key`
    literal `spec_key` (não o hash real de `SpecIdentity.stable_key()`) —
    usado por testes que exercitam SPEC_NAVIGATION/GROUP_DETAIL/finalização
    sob um `spec_key` sintético legível (ex.: "spec-1"). Necessário desde o
    hardening final de 004: `process_capture()`/`try_finalize_spec_entry()`
    exigem que todo `spec_key` esteja registrado e pertença ao mesmo
    `context` — "identidade ausente" deixou de ser um caso ignorado."""
    conn.execute(
        "INSERT OR IGNORE INTO spec_registry (stable_key, source, manufacturer, "
        "vehicle_model, market, model_code, amayama_catalog_id, production_period_raw, "
        "source_url) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            spec_key,
            context.source,
            context.manufacturer,
            context.vehicle_model,
            context.market,
            model_code,
            amayama_catalog_id,
            "irrelevant for this test",
            "https://x/irrelevant",
        ),
    )


class ThreadProcessHandle:
    """005 hardening (pós-review) — duplo de `multiprocessing.process.BaseProcess`
    (`orchestration/worker_pool.py::_ProcessHandle`) usado por
    `run_pool()` em teste: roda o `target` numa thread em vez de um
    processo de SO real (sem exigir spawn/Chrome). Compartilhado entre
    `test_worker_pool_run_pool_orchestrator.py`,
    `test_worker_pool_shutdown.py` e `test_worker_pool_worker_exitcode.py`.

    `exitcode` reflete o que um `multiprocessing.Process` real produziria:
    `0` ao terminar normalmente, `1` se o `target` levantou uma exceção não
    tratada (nunca propagada para a thread principal — capturada aqui,
    mesmo comportamento de um processo real, cujo traceback vai para
    stderr mas não derruba o pai). `terminate()` é um no-op documentado —
    Python não oferece uma forma segura de forçar o encerramento de uma
    thread; os testes que dependem de shutdown cooperativo fazem o
    `target` checar `stop_event` periodicamente, como `run_worker_loop()`
    já faz.

    `pid` (005 hardening pós-review, 2ª rodada — race `Process.start()`):
    espelha `threading.Thread.ident` — `None` até `start()` efetivamente
    iniciar a thread real, nunca `None` depois. Mesma semântica pública que
    `multiprocessing.Process.pid` usa para sinalizar "o filho real ainda
    não existe" vs. "já existe"."""

    def __init__(self, target: Callable[..., None], args: tuple[object, ...]) -> None:
        self._target = target
        self._args = args
        self._exception: BaseException | None = None
        self._thread = threading.Thread(target=self._run)
        self.exitcode: int | None = None

    def _run(self) -> None:
        try:
            self._target(*self._args)
        except BaseException as exc:  # noqa: BLE001 - mirrors a real process's exitcode=1
            self._exception = exc

    def start(self) -> None:
        self._thread.start()

    def join(self, timeout: float | None = None) -> None:
        self._thread.join(timeout)
        if not self._thread.is_alive():
            self.exitcode = 1 if self._exception is not None else 0

    def is_alive(self) -> bool:
        return self._thread.is_alive()

    def terminate(self) -> None:
        pass  # documented no-op — see class docstring

    @property
    def pid(self) -> int | None:
        return self._thread.ident
