"""T070 — dry-run sobre estado vazio produz um plano coerente ("nada a fazer
sem descoberta real primeiro"), sem inventar specs (spec.md Edge Cases)."""

from __future__ import annotations

from amayama_scraper.checkpoint.collection_run import FIXED_SCOPE
from amayama_scraper.orchestration.dry_run import ReadOnlyRepos, plan_operation


def test_plan_operation_over_empty_state_reports_nothing_to_do() -> None:
    repos = ReadOnlyRepos(
        get_collection_run=lambda run_id: None,
        list_incomplete_runs=lambda scope: [],
        list_all_spec_identities=list,
        get_current_state=lambda key: None,
        get_authoritative_manifest=lambda key, run_id: None,
        get_pending_groups=lambda run_id, key: [],
    )

    plan = plan_operation(
        repos,
        resume_run_id=None,
        new_run=False,
        scope=FIXED_SCOPE,
        limit_specs=None,
        limit_groups=None,
        spec_filter=None,
        force=None,
    )

    assert plan.discovered_spec_count == 0
    assert plan.specs_to_process == []
    assert plan.already_valid_specs == []
    assert plan.pending_groups_by_spec == {}
    assert plan.specs_without_manifest_yet == []
    assert "new" in plan.run_decision.lower()  # no error, just "would create a new run"
