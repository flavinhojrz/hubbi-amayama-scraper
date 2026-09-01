"""T065 — plan_operation() reflete a mesma decisão de select_run() (DEC-009),
apenas como texto em OperationalPlan.run_decision, sem levantar exceção e
sem gravar nada."""

from __future__ import annotations

from datetime import UTC, datetime

from amayama_scraper.checkpoint.collection_run import FIXED_SCOPE, CollectionRun
from amayama_scraper.orchestration.dry_run import ReadOnlyRepos, plan_operation

_NOW = datetime(2026, 8, 28, tzinfo=UTC)


def _repos(runs: list[CollectionRun] | None = None) -> ReadOnlyRepos:
    by_id = {r.run_id: r for r in (runs or [])}
    return ReadOnlyRepos(
        get_collection_run=by_id.get,
        list_incomplete_runs=lambda scope: [
            r for r in by_id.values() if r.scope == scope and r.completed_at is None
        ],
        list_all_spec_identities=list,
        get_current_state=lambda key: None,
        get_authoritative_manifest=lambda key, run_id: None,
        get_pending_groups=lambda run_id, key: [],
    )


def _plan(repos: ReadOnlyRepos, **overrides: object):
    defaults: dict[str, object] = dict(
        resume_run_id=None,
        new_run=False,
        scope=FIXED_SCOPE,
        limit_specs=None,
        limit_groups=None,
        spec_filter=None,
        force=None,
    )
    defaults.update(overrides)
    return plan_operation(repos, **defaults)  # type: ignore[arg-type]


def test_zero_incomplete_runs_reported_as_would_create_new() -> None:
    plan = _plan(_repos())
    assert "new" in plan.run_decision.lower()


def test_exactly_one_incomplete_run_reported_as_would_auto_resume() -> None:
    plan = _plan(_repos([CollectionRun(run_id="run-1", started_at=_NOW)]))
    assert "run-1" in plan.run_decision
    assert "resume" in plan.run_decision.lower()


def test_two_incomplete_runs_reported_as_ambiguous_never_raises() -> None:
    plan = _plan(
        _repos(
            [
                CollectionRun(run_id="run-a", started_at=_NOW),
                CollectionRun(run_id="run-b", started_at=_NOW),
            ]
        )
    )
    assert "ambigu" in plan.run_decision.lower() or "ambig" in plan.run_decision.lower()
    assert "run-a" in plan.run_decision and "run-b" in plan.run_decision


def test_explicit_resume_of_valid_run_reported() -> None:
    plan = _plan(_repos([CollectionRun(run_id="run-1", started_at=_NOW)]), resume_run_id="run-1")
    assert "run-1" in plan.run_decision


def test_explicit_resume_of_invalid_run_reported_never_raises() -> None:
    plan = _plan(_repos(), resume_run_id="does-not-exist")
    assert "invalid" in plan.run_decision.lower() or "reject" in plan.run_decision.lower()


def test_new_run_flag_reported_as_would_create_new() -> None:
    plan = _plan(_repos([CollectionRun(run_id="run-1", started_at=_NOW)]), new_run=True)
    assert "new" in plan.run_decision.lower()
