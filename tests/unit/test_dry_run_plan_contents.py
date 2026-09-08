"""T066 — plan_operation(): specs_to_process/already_valid_specs/
pending_groups_by_spec/specs_without_manifest_yet refletem exatamente o
estado persistido, aplicando --spec/--limit-specs/--limit-groups/--force
como uma execução real aplicaria (DEC-009)."""

from __future__ import annotations

from datetime import date

from amayama_scraper.checkpoint.collection_run import FIXED_SCOPE, CollectionRun
from amayama_scraper.domain.current_state import CurrentSpecState
from amayama_scraper.domain.identity import SpecIdentity
from amayama_scraper.orchestration.dry_run import ReadOnlyRepos, plan_operation


def _identity(catalog_id: str) -> SpecIdentity:
    return SpecIdentity(
        source="AMAYAMA",
        manufacturer="VOLKSWAGEN",
        vehicle_model="AMAROK",
        market="AMA-BR",
        model_code="S7BC8A",
        amayama_catalog_id=catalog_id,
        production_period_raw="2022.06 - ...",
        source_url=f"https://x/{catalog_id}",
        production_start=date(2022, 6, 1),
    )


_SPEC_A = _identity("62184")
_SPEC_B = _identity("61189")
_KEY_A = _SPEC_A.stable_key()
_KEY_B = _SPEC_B.stable_key()

_RUN = CollectionRun(run_id="run-1")


def _repos(
    *,
    current_states: dict[str, CurrentSpecState] | None = None,
    manifests: dict[str, object] | None = None,
    pending: dict[str, list[tuple[str, str]]] | None = None,
) -> ReadOnlyRepos:
    current_states = current_states or {}
    manifests = manifests or {}
    pending = pending or {}
    return ReadOnlyRepos(
        get_collection_run={_RUN.run_id: _RUN}.get,
        list_incomplete_runs=lambda scope: [_RUN] if _RUN.scope == scope else [],
        list_all_spec_identities=lambda: [_SPEC_A, _SPEC_B],
        get_current_state=lambda key: current_states.get(key),
        get_authoritative_manifest=lambda key, run_id: manifests.get(key),
        get_pending_groups=lambda run_id, key: pending.get(key, []),
    )


def _plan(repos: ReadOnlyRepos, **overrides: object):
    defaults: dict[str, object] = dict(
        resume_run_id="run-1",
        new_run=False,
        scope=FIXED_SCOPE,
        limit_specs=None,
        limit_groups=None,
        spec_filter=None,
        force=None,
    )
    defaults.update(overrides)
    return plan_operation(repos, **defaults)  # type: ignore[arg-type]


def test_discovered_spec_count_reflects_all_identities() -> None:
    plan = _plan(_repos())
    assert plan.discovered_spec_count == 2


def test_already_valid_spec_is_excluded_from_specs_to_process() -> None:
    current = CurrentSpecState(
        spec_identity_ref=_KEY_A, latest_snapshot_id="snap-1", cluster_key=None
    )
    plan = _plan(_repos(current_states={_KEY_A: current}))
    assert _KEY_A in plan.already_valid_specs
    assert _KEY_A not in plan.specs_to_process
    assert _KEY_B in plan.specs_to_process


def test_force_includes_already_valid_spec_in_specs_to_process() -> None:
    current = CurrentSpecState(
        spec_identity_ref=_KEY_A, latest_snapshot_id="snap-1", cluster_key=None
    )
    plan = _plan(_repos(current_states={_KEY_A: current}), force=[_KEY_A])
    assert _KEY_A in plan.specs_to_process
    assert _KEY_A not in plan.already_valid_specs


def test_spec_without_manifest_yet_is_reported_separately() -> None:
    plan = _plan(_repos())
    assert set(plan.specs_without_manifest_yet) == {_KEY_A, _KEY_B}
    assert plan.pending_groups_by_spec == {}


def test_spec_with_manifest_reports_pending_groups() -> None:
    plan = _plan(
        _repos(
            manifests={_KEY_A: object()},
            pending={_KEY_A: [("engine", "100"), ("body", "800")]},
        )
    )
    assert plan.pending_groups_by_spec[_KEY_A] == [("engine", "100"), ("body", "800")]
    assert _KEY_A not in plan.specs_without_manifest_yet


def test_limit_groups_truncates_pending_groups() -> None:
    plan = _plan(
        _repos(
            manifests={_KEY_A: object()}, pending={_KEY_A: [("engine", "100"), ("body", "800")]}
        ),
        limit_groups=1,
    )
    assert plan.pending_groups_by_spec[_KEY_A] == [("engine", "100")]


def test_limit_specs_truncates_specs_to_process() -> None:
    plan = _plan(_repos(), limit_specs=1)
    assert len(plan.specs_to_process) == 1


def test_spec_filter_restricts_to_named_specs() -> None:
    plan = _plan(_repos(), spec_filter=[_KEY_A])
    assert plan.specs_to_process == [_KEY_A]
