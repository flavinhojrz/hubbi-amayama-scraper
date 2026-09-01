"""T041 — semântica de restart: select_run() reconstrói a decisão inteiramente
a partir do estado persistido em disco, nunca de memória do processo
(FR-018, SC-003, spec.md Edge Cases "reinício da máquina").

Usa um arquivo SQLite real (não :memory:) e uma SEGUNDA conexão totalmente
independente para simular um novo processo, sem reaproveitar nenhum objeto
Python do "processo" anterior.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from functools import partial
from pathlib import Path

from amayama_scraper.checkpoint.collection_run import FIXED_SCOPE, CollectionRun
from amayama_scraper.orchestration.run_selection import select_run
from amayama_scraper.persistence.db import connect
from amayama_scraper.persistence.migrations.runner import run_migrations
from amayama_scraper.persistence.repositories.checkpoint_repo import (
    get_collection_run,
    list_incomplete_runs,
    save_collection_run,
)

_NOW = datetime(2026, 8, 28, tzinfo=UTC)


def _select(conn, **overrides: object):
    defaults: dict[str, object] = dict(
        resume_run_id=None,
        new_run=False,
        scope=FIXED_SCOPE,
        now=_NOW,
        run_id_factory=lambda: str(uuid.uuid4()),
        get_collection_run=partial(get_collection_run, conn),
        list_incomplete_runs=partial(list_incomplete_runs, conn),
        save_collection_run=partial(save_collection_run, conn),
    )
    defaults.update(overrides)
    return select_run(**defaults)  # type: ignore[arg-type]


def test_second_process_reaches_same_resume_decision_from_disk_state(tmp_path: Path) -> None:
    db_path = str(tmp_path / "amayama.db")

    # "Processo 1": inicia uma execução (nova run) e depois "morre" (conexão fechada,
    # nenhum objeto Python sobrevive).
    conn_1 = connect(db_path)
    run_migrations(conn_1)
    first_result = _select(conn_1)
    assert first_result.created_new is True
    original_run_id = first_result.run.run_id
    conn_1.close()
    del conn_1

    # "Processo 2": nova conexão independente, nenhum estado em memória reaproveitado.
    conn_2 = connect(db_path)
    second_result = _select(conn_2, resume_run_id=original_run_id)

    assert second_result.created_new is False
    assert second_result.run.run_id == original_run_id


def test_second_process_sees_same_ambiguity_as_first_would_have(tmp_path: Path) -> None:
    db_path = str(tmp_path / "amayama.db")

    conn_1 = connect(db_path)
    run_migrations(conn_1)
    save_collection_run(conn_1, CollectionRun(run_id="run-a", started_at=_NOW))
    save_collection_run(conn_1, CollectionRun(run_id="run-b", started_at=_NOW))
    conn_1.close()
    del conn_1

    conn_2 = connect(db_path)
    candidates = list_incomplete_runs(conn_2, FIXED_SCOPE)
    assert {r.run_id for r in candidates} == {"run-a", "run-b"}
