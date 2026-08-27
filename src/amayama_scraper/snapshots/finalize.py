"""finalize_spec_entry() — contracts/snapshot-contract.md.

Duas fases, exatamente como documentado: `plan_finalization()` (Fase 1 —
leitura + computação pura, nenhuma escrita) e `commit_finalization()`
(Fase 2 — única transação de escrita). `finalize_spec_entry()` compõe as
duas. Todos os repositórios são recebidos como *ports* (snapshots/ports.py,
ingestion/ports.py) — nunca uma dependência direta de `persistence/`/
`sqlite3` (contracts/ports-contract.md fecha `snapshots/` fora do escopo de
quem conhece adapters concretos).

Nenhum `ParsedGroupDetail`/árvore precisa ter sobrevivido em memória entre
processos: a Fase 1 reconstrói tudo a partir do que está persistido
(`manifest_repo`, `checkpoint_repo`, `reconstruct_raw_content()` +
`parse_group_detail()`) — um restart do processo entre a aceitação dos
grupos e a finalização não perde nada (data-model.md §13c).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from amayama_scraper.checkpoint.checkpoint_entry import CheckpointEntry
from amayama_scraper.domain.hierarchy import Category, Group, Schema
from amayama_scraper.fingerprints.types import FingerprintSet
from amayama_scraper.fingerprints.version import compute_fingerprint_set
from amayama_scraper.ingestion.ports import (
    RawBlobStore,
    RawCaptureRepository,
    reconstruct_raw_content,
)
from amayama_scraper.normalization.version import apply_normalization
from amayama_scraper.parsing.assembly import assemble_spec_tree
from amayama_scraper.parsing.group_detail import parse_group_detail
from amayama_scraper.parsing.results import ParsedGroupDetail
from amayama_scraper.snapshots.idempotency import compute_idempotency_key
from amayama_scraper.snapshots.ports import (
    CheckpointQueryRepository,
    CurrentStateRepository,
    FingerprintWriteRepository,
    ManifestRepository,
    SnapshotRepository,
)
from amayama_scraper.snapshots.snapshot import (
    SnapshotState,
    SpecSnapshot,
    assign_snapshot_state,
    compute_collection_complete,
)


@dataclass(frozen=True, slots=True)
class FinalizationPlan:
    """Resultado completo da Fase 1 — tudo que a Fase 2 precisa, já calculado."""

    spec_key: str
    run_id: str
    spec_identity_ref: str
    idempotency_key: str
    collection_complete: bool
    state: SnapshotState
    fingerprints: FingerprintSet
    parser_version: str
    counts: dict[str, int]


def _normalize_tree(tree: tuple[Category, ...]) -> tuple[Category, ...]:
    return tuple(
        Category(
            category_slug=category.category_slug,
            groups=tuple(
                Group(
                    group_id=group.group_id,
                    schemas=tuple(
                        Schema(
                            schema_id=schema.schema_id,
                            parts=tuple(apply_normalization(part).part for part in schema.parts),
                        )
                        for schema in group.schemas
                    ),
                )
                for group in category.groups
            ),
        )
        for category in tree
    )


def plan_finalization(
    *,
    spec_key: str,
    run_id: str,
    spec_identity_ref: str,
    manifest_repo: ManifestRepository,
    checkpoint_repo: CheckpointQueryRepository,
    capture_repo: RawCaptureRepository,
    blob_store: RawBlobStore,
) -> FinalizationPlan | None:
    manifest = manifest_repo.get_authoritative(spec_key, run_id)
    if manifest is None:
        return None

    accepted_entries: list[CheckpointEntry] = checkpoint_repo.list_accepted(run_id, spec_key)
    collection_complete = compute_collection_complete(manifest, accepted_entries)

    group_details: dict[tuple[str, str], ParsedGroupDetail] = {}
    parser_version = "amayama-parser-v1"
    for entry in accepted_entries:
        assert entry.raw_capture_id is not None  # ACCEPTED always carries one
        raw_content = reconstruct_raw_content(entry.raw_capture_id, capture_repo, blob_store)
        parsed = parse_group_detail(
            raw_content.decode("utf-8"),
            category_slug=entry.category_slug,
            group_id=entry.group_id,
        )
        group_details[(entry.category_slug, entry.group_id)] = parsed
        if parsed.parser_version:
            parser_version = parsed.parser_version

    has_critical_error = any(gd.critical_error is not None for gd in group_details.values())

    assembled_tree = assemble_spec_tree(manifest, group_details)
    normalized_tree = _normalize_tree(assembled_tree)
    fingerprints = compute_fingerprint_set(normalized_tree)

    idempotency_key = compute_idempotency_key(run_id, spec_key, accepted_entries)
    state = assign_snapshot_state(
        has_critical_error=has_critical_error, collection_complete=collection_complete
    )

    counts = {
        "categories": len(assembled_tree),
        "groups": sum(len(c.groups) for c in assembled_tree),
        "schemas": sum(len(g.schemas) for c in assembled_tree for g in c.groups),
        "parts": sum(len(s.parts) for c in assembled_tree for g in c.groups for s in g.schemas),
    }

    return FinalizationPlan(
        spec_key=spec_key,
        run_id=run_id,
        spec_identity_ref=spec_identity_ref,
        idempotency_key=idempotency_key,
        collection_complete=collection_complete,
        state=state,
        fingerprints=fingerprints,
        parser_version=parser_version,
        counts=counts,
    )


def commit_finalization(
    plan: FinalizationPlan,
    *,
    snapshot_id_factory: Callable[[], str],
    now_factory: Callable[[], datetime],
    snapshot_repo: SnapshotRepository,
    fingerprint_repo: FingerprintWriteRepository,
    current_state_repo: CurrentStateRepository,
    run_in_transaction: Callable[[Callable[[], SpecSnapshot]], SpecSnapshot],
) -> SpecSnapshot:
    def _commit() -> SpecSnapshot:
        existing = snapshot_repo.get_by_idempotency_key(plan.idempotency_key)
        if existing is not None:
            # idempotent retry — never insert a second snapshot for this key
            current_state_repo.materialize(plan.spec_identity_ref)
            return existing

        previous = current_state_repo.materialize(plan.spec_identity_ref)

        new_snapshot = SpecSnapshot(
            snapshot_id=snapshot_id_factory(),
            spec_identity_ref=plan.spec_identity_ref,
            idempotency_key=plan.idempotency_key,
            collected_at=now_factory(),
            parser_version=plan.parser_version,
            normalizer_version="amayama-normalizer-v1",
            fingerprint_version=plan.fingerprints.fingerprint_version,
            collection_complete=plan.collection_complete,
            structure_hash=plan.fingerprints.structure_hash,
            spec_parts_hash=plan.fingerprints.spec_parts_hash,
            schema_semantic_hash=plan.fingerprints.schema_semantic_hash,
            image_hash=plan.fingerprints.image_hash,
            state=plan.state,
            counts=plan.counts,
        )
        snapshot_id = snapshot_repo.save(new_snapshot)
        fingerprint_repo.update(snapshot_id, plan.fingerprints)

        # last-known-good (ponto 17 do PLAN): um snapshot novo só supersede o
        # anterior VALID/STALE quando ele próprio é um sucessor legítimo
        # (VALID/INCOMPLETE) — um novo snapshot INVALID (critical_error) NUNCA
        # apaga/transiciona o último bom conhecido (data-model.md §6 tabela de estados).
        is_legitimate_successor = plan.state in (SnapshotState.VALID, SnapshotState.INCOMPLETE)
        if (
            is_legitimate_successor
            and previous is not None
            and previous.latest_snapshot_id != snapshot_id
        ):
            snapshot_repo.supersede(previous.latest_snapshot_id)

        current_state_repo.materialize(plan.spec_identity_ref)
        return new_snapshot

    return run_in_transaction(_commit)


def finalize_spec_entry(
    *,
    spec_key: str,
    run_id: str,
    spec_identity_ref: str,
    manifest_repo: ManifestRepository,
    checkpoint_repo: CheckpointQueryRepository,
    capture_repo: RawCaptureRepository,
    blob_store: RawBlobStore,
    snapshot_repo: SnapshotRepository,
    fingerprint_repo: FingerprintWriteRepository,
    current_state_repo: CurrentStateRepository,
    run_in_transaction: Callable[[Callable[[], SpecSnapshot]], SpecSnapshot],
    snapshot_id_factory: Callable[[], str],
    now_factory: Callable[[], datetime],
) -> SpecSnapshot | None:
    plan = plan_finalization(
        spec_key=spec_key,
        run_id=run_id,
        spec_identity_ref=spec_identity_ref,
        manifest_repo=manifest_repo,
        checkpoint_repo=checkpoint_repo,
        capture_repo=capture_repo,
        blob_store=blob_store,
    )
    if plan is None:
        return None
    return commit_finalization(
        plan,
        snapshot_id_factory=snapshot_id_factory,
        now_factory=now_factory,
        snapshot_repo=snapshot_repo,
        fingerprint_repo=fingerprint_repo,
        current_state_repo=current_state_repo,
        run_in_transaction=run_in_transaction,
    )
