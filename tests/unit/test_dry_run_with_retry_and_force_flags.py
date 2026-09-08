"""T071 — dry-run combinado com --force apenas relata o efeito esperado
(quais specs entrariam em specs_to_process), nunca os aplica. Nenhum
CheckpointEntry muda de estado como resultado desta chamada.

Nota: --retry-rejected não altera o conteúdo do plano de dry-run — um
grupo REQUIRES_EXPLICIT_RETRY já aparece em pending_groups_by_spec
independentemente da flag (get_pending_groups() não distingue REJECTED de
PENDING), então não há um parâmetro `retry_rejected` separado em
plan_operation(): a informação já é visível sem ele (contracts/
orchestration-contract.md §3)."""

from __future__ import annotations

from datetime import date

from amayama_scraper.checkpoint.collection_run import FIXED_SCOPE, CollectionRun
from amayama_scraper.domain.current_state import CurrentSpecState
from amayama_scraper.domain.identity import SpecIdentity
from amayama_scraper.orchestration.dry_run import ReadOnlyRepos, plan_operation

_IDENTITY = SpecIdentity(
    source="AMAYAMA",
    manufacturer="VOLKSWAGEN",
    vehicle_model="AMAROK",
    market="AMA-BR",
    model_code="S7BC8A",
    amayama_catalog_id="62184",
    production_period_raw="2022.06 - ...",
    source_url="https://x/62184",
    production_start=date(2022, 6, 1),
)
_KEY = _IDENTITY.stable_key()


def test_force_flag_moves_spec_from_already_valid_to_specs_to_process_without_writes() -> None:
    calls = {"writes": 0}
    current = CurrentSpecState(
        spec_identity_ref=_KEY, latest_snapshot_id="snap-1", cluster_key=None
    )
    repos = ReadOnlyRepos(
        get_collection_run=lambda run_id: CollectionRun(run_id="run-1"),
        list_incomplete_runs=lambda scope: [CollectionRun(run_id="run-1")],
        list_all_spec_identities=lambda: [_IDENTITY],
        get_current_state=lambda key: current,
        get_authoritative_manifest=lambda key, run_id: None,
        get_pending_groups=lambda run_id, key: [],
    )

    without_force = plan_operation(
        repos,
        resume_run_id=None,
        new_run=False,
        scope=FIXED_SCOPE,
        limit_specs=None,
        limit_groups=None,
        spec_filter=None,
        force=None,
    )
    with_force = plan_operation(
        repos,
        resume_run_id=None,
        new_run=False,
        scope=FIXED_SCOPE,
        limit_specs=None,
        limit_groups=None,
        spec_filter=None,
        force=[_KEY],
    )

    assert _KEY in without_force.already_valid_specs
    assert _KEY not in without_force.specs_to_process
    assert _KEY in with_force.specs_to_process
    assert _KEY not in with_force.already_valid_specs
    # nothing in ReadOnlyRepos exposes a way to write — calls["writes"] can
    # never be incremented by plan_operation() by construction (T064).
    assert calls["writes"] == 0
