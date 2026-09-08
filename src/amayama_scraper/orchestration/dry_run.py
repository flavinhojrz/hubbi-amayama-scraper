"""plan_operation() — DEC-009, contracts/orchestration-contract.md §3.

Mutação é estruturalmente impossível: ReadOnlyRepos não expõe nenhuma
função de escrita (nem `save_collection_run`, nem `process_capture`, nem
`transport.navigate`) — não é apenas uma promessa comportamental, é uma
propriedade da assinatura de tipo (verificável por mypy --strict, T126).
Reproduz a mesma decisão de run_selection.select_run() e os mesmos filtros
do driver real (collection_driver.py), mas nunca escreve nada.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from amayama_scraper.checkpoint.collection_run import CollectionRun
from amayama_scraper.domain.current_state import CurrentSpecState
from amayama_scraper.domain.identity import SpecIdentity


@dataclass(frozen=True, slots=True)
class ReadOnlyRepos:
    get_collection_run: Callable[[str], CollectionRun | None]
    list_incomplete_runs: Callable[[str], list[CollectionRun]]
    list_all_spec_identities: Callable[[], list[SpecIdentity]]
    get_current_state: Callable[[str], CurrentSpecState | None]
    get_authoritative_manifest: Callable[[str, str], object | None]
    get_pending_groups: Callable[[str, str], list[tuple[str, str]]]


@dataclass(frozen=True, slots=True)
class OperationalPlan:
    run_decision: str
    discovered_spec_count: int
    specs_to_process: list[str] = field(default_factory=list)
    already_valid_specs: list[str] = field(default_factory=list)
    pending_groups_by_spec: dict[str, list[tuple[str, str]]] = field(default_factory=dict)
    specs_without_manifest_yet: list[str] = field(default_factory=list)


def _describe_run_decision(
    repos: ReadOnlyRepos, *, resume_run_id: str | None, new_run: bool, scope: str
) -> tuple[str, str | None]:
    """Reproduz select_run() (DEC-005) como leitura pura — nunca levanta,
    apenas descreve o que uma execução real faria/rejeitaria."""
    if resume_run_id is not None:
        run = repos.get_collection_run(resume_run_id)
        if run is None or run.scope != scope or run.completed_at is not None:
            return (
                f"--resume {resume_run_id} is INVALID (unknown run, incompatible scope, "
                "or already completed) — a real execution would reject this with an error",
                None,
            )
        return (f"would resume the explicitly requested run {resume_run_id}", resume_run_id)

    if new_run:
        return ("would create a new run (--new-run forces this)", None)

    candidates = repos.list_incomplete_runs(scope)
    if len(candidates) == 0:
        return ("would create a new run (no incomplete compatible runs found)", None)
    if len(candidates) == 1:
        run_id = candidates[0].run_id
        return (f"would auto-resume the only incomplete compatible run ({run_id})", run_id)
    run_ids = ", ".join(sorted(c.run_id for c in candidates))
    return (
        f"AMBIGUOUS: {len(candidates)} incomplete compatible runs found ({run_ids}) — "
        "a real execution would require explicit --resume <run_id> or --new-run, "
        "never choosing automatically",
        None,
    )


def plan_operation(
    repos: ReadOnlyRepos,
    *,
    resume_run_id: str | None,
    new_run: bool,
    scope: str,
    limit_specs: int | None,
    limit_groups: int | None,
    spec_filter: list[str] | None,
    force: list[str] | None,
) -> OperationalPlan:
    run_decision, resolved_run_id = _describe_run_decision(
        repos, resume_run_id=resume_run_id, new_run=new_run, scope=scope
    )

    all_identities = repos.list_all_spec_identities()
    all_keys = [identity.stable_key() for identity in all_identities]

    force_set = set(force or [])
    candidate_keys = [k for k in all_keys if spec_filter is None or k in set(spec_filter)]

    already_valid: list[str] = []
    eligible: list[str] = []
    for key in candidate_keys:
        current_state = repos.get_current_state(key)
        if current_state is not None and key not in force_set:
            already_valid.append(key)
        else:
            eligible.append(key)

    specs_to_process = eligible if limit_specs is None else eligible[:limit_specs]

    pending_groups_by_spec: dict[str, list[tuple[str, str]]] = {}
    specs_without_manifest_yet: list[str] = []
    if resolved_run_id is not None:
        for key in specs_to_process:
            manifest = repos.get_authoritative_manifest(key, resolved_run_id)
            if manifest is None:
                specs_without_manifest_yet.append(key)
                continue
            pending = repos.get_pending_groups(resolved_run_id, key)
            if limit_groups is not None:
                pending = pending[:limit_groups]
            pending_groups_by_spec[key] = pending
    else:
        # No concrete run resolved (would-create-new/ambiguous/invalid) — no
        # manifest/pending-groups state exists yet for that hypothetical run.
        specs_without_manifest_yet = list(specs_to_process)

    return OperationalPlan(
        run_decision=run_decision,
        discovered_spec_count=len(all_identities),
        specs_to_process=specs_to_process,
        already_valid_specs=already_valid,
        pending_groups_by_spec=pending_groups_by_spec,
        specs_without_manifest_yet=specs_without_manifest_yet,
    )
