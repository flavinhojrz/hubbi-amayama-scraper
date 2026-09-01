"""select_run() — DEC-005, contracts/orchestration-contract.md §1.

Função pura sobre callables injetadas — nenhum sqlite3/selenium importado
aqui (testável 100% em memória). Nunca escolhe heuristicamente entre
execuções incompletas concorrentes: zero candidatos cria uma nova execução;
exatamente um resume automaticamente; dois ou mais exigem `--resume`
explícito do operador.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from amayama_scraper.checkpoint.collection_run import CollectionRun


class IncompatibleResumeRunError(ValueError):
    """--resume aponta para um run inexistente, de scope diferente, ou já completo."""


class AmbiguousResumeError(ValueError):
    """Duas ou mais CollectionRun incompletas compatíveis — nunca escolhida por heurística."""

    def __init__(self, candidates: list[CollectionRun]) -> None:
        self.candidates = candidates
        run_ids = ", ".join(run.run_id for run in candidates)
        super().__init__(
            f"{len(candidates)} incomplete runs compatible with this scope exist "
            f"({run_ids}) — pass --resume <run_id> explicitly or --new-run"
        )


@dataclass(frozen=True, slots=True)
class RunSelectionResult:
    run: CollectionRun
    created_new: bool


def select_run(
    *,
    resume_run_id: str | None,
    new_run: bool,
    scope: str,
    now: datetime,
    run_id_factory: Callable[[], str],
    get_collection_run: Callable[[str], CollectionRun | None],
    list_incomplete_runs: Callable[[str], list[CollectionRun]],
    save_collection_run: Callable[[CollectionRun], None],
) -> RunSelectionResult:
    if resume_run_id is not None:
        run = get_collection_run(resume_run_id)
        if run is None or run.scope != scope or run.completed_at is not None:
            raise IncompatibleResumeRunError(
                f"run_id {resume_run_id!r} is not a compatible, incomplete run for scope {scope!r}"
            )
        return RunSelectionResult(run=run, created_new=False)

    if new_run:
        return _create_new_run(
            scope=scope,
            now=now,
            run_id_factory=run_id_factory,
            save_collection_run=save_collection_run,
        )

    candidates = list_incomplete_runs(scope)
    if len(candidates) == 0:
        return _create_new_run(
            scope=scope,
            now=now,
            run_id_factory=run_id_factory,
            save_collection_run=save_collection_run,
        )
    if len(candidates) == 1:
        return RunSelectionResult(run=candidates[0], created_new=False)
    raise AmbiguousResumeError(candidates)


def _create_new_run(
    *,
    scope: str,
    now: datetime,
    run_id_factory: Callable[[], str],
    save_collection_run: Callable[[CollectionRun], None],
) -> RunSelectionResult:
    run = CollectionRun(run_id=run_id_factory(), scope=scope, started_at=now)
    save_collection_run(run)
    return RunSelectionResult(run=run, created_new=True)
