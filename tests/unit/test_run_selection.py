"""T033-T038 — select_run() (DEC-005, contracts/orchestration-contract.md §1).

Função pura sobre callables injetadas — nenhum sqlite3/selenium importado
por orchestration/run_selection.py. Nunca escolhe heuristicamente entre
execuções incompletas concorrentes.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from amayama_scraper.checkpoint.collection_run import FIXED_SCOPE, CollectionRun
from amayama_scraper.orchestration.run_selection import (
    AmbiguousResumeError,
    IncompatibleResumeRunError,
    select_run,
)

_NOW = datetime(2026, 8, 28, tzinfo=UTC)


class _FakeRunStore:
    def __init__(self, runs: list[CollectionRun] | None = None) -> None:
        self._by_id: dict[str, CollectionRun] = {r.run_id: r for r in (runs or [])}
        self.saved: list[CollectionRun] = []

    def get(self, run_id: str) -> CollectionRun | None:
        return self._by_id.get(run_id)

    def list_incomplete(self, scope: str) -> list[CollectionRun]:
        return [r for r in self._by_id.values() if r.scope == scope and r.completed_at is None]

    def save(self, run: CollectionRun) -> None:
        self.saved.append(run)
        self._by_id[run.run_id] = run


def _select(store: _FakeRunStore, **overrides: object) -> object:
    defaults: dict[str, object] = dict(
        resume_run_id=None,
        new_run=False,
        scope=FIXED_SCOPE,
        now=_NOW,
        run_id_factory=lambda: "new-run-id",
        get_collection_run=store.get,
        list_incomplete_runs=store.list_incomplete,
        save_collection_run=store.save,
    )
    defaults.update(overrides)
    return select_run(**defaults)  # type: ignore[arg-type]


# T033 — zero incompletas compatíveis → cria nova


def test_zero_incomplete_runs_creates_new_run() -> None:
    store = _FakeRunStore()
    result = _select(store)
    assert result.created_new is True
    assert result.run.run_id == "new-run-id"
    assert store.saved == [result.run]


# T034 — exatamente uma → resume automático, nenhuma escrita


def test_exactly_one_incomplete_run_auto_resumes_without_writing() -> None:
    existing = CollectionRun(run_id="run-1", started_at=_NOW)
    store = _FakeRunStore([existing])
    result = _select(store)
    assert result.created_new is False
    assert result.run == existing
    assert store.saved == []


# T035 — duas ou mais → AmbiguousResumeError, nenhuma escrita


def test_two_or_more_incomplete_runs_raises_ambiguous_without_writing() -> None:
    run_a = CollectionRun(run_id="run-a", started_at=_NOW)
    run_b = CollectionRun(run_id="run-b", started_at=_NOW)
    store = _FakeRunStore([run_a, run_b])
    with pytest.raises(AmbiguousResumeError) as exc_info:
        _select(store)
    candidate_ids = {r.run_id for r in exc_info.value.candidates}
    assert candidate_ids == {"run-a", "run-b"}
    assert store.saved == []


# T036 — --resume válido → usa sem gravar


def test_explicit_resume_of_compatible_incomplete_run_returns_it_without_writing() -> None:
    existing = CollectionRun(run_id="run-1", started_at=_NOW)
    store = _FakeRunStore([existing])
    result = _select(store, resume_run_id="run-1")
    assert result.created_new is False
    assert result.run == existing
    assert store.saved == []


# T037 — --resume incompatível (scope diferente / completo / inexistente) → erro


def test_explicit_resume_of_completed_run_raises_incompatible() -> None:
    completed = CollectionRun(run_id="run-done", started_at=_NOW, completed_at=_NOW)
    store = _FakeRunStore([completed])
    with pytest.raises(IncompatibleResumeRunError):
        _select(store, resume_run_id="run-done")


def test_explicit_resume_of_nonexistent_run_raises_incompatible() -> None:
    store = _FakeRunStore()
    with pytest.raises(IncompatibleResumeRunError):
        _select(store, resume_run_id="does-not-exist")


def test_explicit_resume_of_different_scope_raises_incompatible() -> None:
    """Também cobre o requisito multi-modelo: --resume de um run de outro
    modelo/mercado (scope diferente) é sempre rejeitado, nunca retomado."""
    other_model_run = CollectionRun(
        run_id="run-other-model", scope="AMAYAMA:VOLKSWAGEN:OTHER-MODEL:AMA-BR", started_at=_NOW
    )
    store = _FakeRunStore([other_model_run])
    with pytest.raises(IncompatibleResumeRunError):
        _select(store, resume_run_id="run-other-model")


# T038 — --new-run sempre cria, mesmo com incompleta compatível existente


def test_new_run_flag_always_creates_even_with_compatible_incomplete_existing() -> None:
    existing = CollectionRun(run_id="run-1", started_at=_NOW)
    store = _FakeRunStore([existing])
    result = _select(store, new_run=True)
    assert result.created_new is True
    assert result.run.run_id == "new-run-id"
    assert store.saved == [result.run]
    # the pre-existing incomplete run is untouched
    assert store.get("run-1") == existing
