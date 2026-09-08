"""compare_specs() — spec.md US4, plan.md.

Puro. Reaproveita equivalence.evaluate.evaluate_equivalence() para a relação
de hashes — nunca reimplementa comparação. Diff de grupos vem de
spec_group_manifest (não existe tabela de parts — spec.md "Fora de escopo").
"""

from __future__ import annotations

from amayama_scraper.analysis.types import (
    GroupSetDiff,
    HashComparison,
    HashComparisonState,
    ScopeIdentifier,
    SpecComparison,
)
from amayama_scraper.domain.identity import SpecIdentity
from amayama_scraper.domain.manifest import SpecGroupManifest
from amayama_scraper.equivalence.evaluate import evaluate_equivalence
from amayama_scraper.fingerprints.types import UNAVAILABLE_HASH
from amayama_scraper.snapshots.snapshot import SpecSnapshot

_ALL_HASHES_UNAVAILABLE = HashComparison(
    structure_hash=HashComparisonState.UNAVAILABLE,
    spec_parts_hash=HashComparisonState.UNAVAILABLE,
    schema_semantic_hash=HashComparisonState.UNAVAILABLE,
    image_hash=HashComparisonState.UNAVAILABLE,
)


def _equivalence_scope(identity: SpecIdentity) -> str:
    """Deriva o scope normativo ("AMAYAMA:VOLKSWAGEN:AMAROK:AMA-BR") a partir
    dos próprios campos de identidade da spec — nunca de um scope externo
    compartilhado. Codex finding #1: comparar duas specs de mercados/modelos
    diferentes precisa produzir scope_a != scope_b (e portanto
    comparison_valid=False/UNKNOWN), o que só é garantido derivando cada lado
    independentemente."""
    return (
        f"{identity.source.strip().upper()}:{identity.manufacturer.strip().upper()}:"
        f"{identity.vehicle_model.strip().upper()}:{identity.market.strip().upper()}"
    )


def _compare_single_hash(value_a: str, value_b: str) -> HashComparisonState:
    if value_a == UNAVAILABLE_HASH or value_b == UNAVAILABLE_HASH:
        return HashComparisonState.UNAVAILABLE
    return HashComparisonState.EQUAL if value_a == value_b else HashComparisonState.DIFFERENT


def compare_specs(
    scope: ScopeIdentifier,
    identity_a: SpecIdentity,
    identity_b: SpecIdentity,
    snapshot_a: SpecSnapshot | None,
    snapshot_b: SpecSnapshot | None,
    manifest_a: SpecGroupManifest | None,
    manifest_b: SpecGroupManifest | None,
) -> SpecComparison:
    equivalence = None
    equivalence_unavailable_reason = None
    hash_comparison = _ALL_HASHES_UNAVAILABLE

    if snapshot_a is not None and snapshot_b is not None:
        equivalence = evaluate_equivalence(
            snapshot_a,
            snapshot_b,
            scope_a=_equivalence_scope(identity_a),
            scope_b=_equivalence_scope(identity_b),
        )
        if equivalence.comparison_valid:
            hash_comparison = HashComparison(
                structure_hash=_compare_single_hash(
                    snapshot_a.structure_hash, snapshot_b.structure_hash
                ),
                spec_parts_hash=_compare_single_hash(
                    snapshot_a.spec_parts_hash, snapshot_b.spec_parts_hash
                ),
                schema_semantic_hash=_compare_single_hash(
                    snapshot_a.schema_semantic_hash, snapshot_b.schema_semantic_hash
                ),
                image_hash=_compare_single_hash(snapshot_a.image_hash, snapshot_b.image_hash),
            )
    else:
        missing = []
        if snapshot_a is None:
            missing.append(identity_a.display_key())
        if snapshot_b is None:
            missing.append(identity_b.display_key())
        equivalence_unavailable_reason = (
            f"sem snapshot para: {', '.join(missing)} — comparação de hash indisponível"
        )

    group_diff = None
    group_diff_unavailable_reason = None
    if manifest_a is not None and manifest_b is not None:
        keys_a = manifest_a.expected_group_keys()
        keys_b = manifest_b.expected_group_keys()
        group_diff = GroupSetDiff(
            only_in_a=keys_a - keys_b,
            only_in_b=keys_b - keys_a,
            shared=keys_a & keys_b,
        )
    else:
        missing = []
        if manifest_a is None:
            missing.append(identity_a.display_key())
        if manifest_b is None:
            missing.append(identity_b.display_key())
        group_diff_unavailable_reason = (
            f"sem manifest completo para: {', '.join(missing)} — diff de grupos indisponível"
        )

    return SpecComparison(
        scope=scope,
        stable_key_a=identity_a.stable_key(),
        stable_key_b=identity_b.stable_key(),
        display_key_a=identity_a.display_key(),
        display_key_b=identity_b.display_key(),
        counts_a=dict(snapshot_a.counts) if snapshot_a is not None else None,
        counts_b=dict(snapshot_b.counts) if snapshot_b is not None else None,
        equivalence=equivalence,
        equivalence_unavailable_reason=equivalence_unavailable_reason,
        hash_comparison=hash_comparison,
        group_diff=group_diff,
        group_diff_unavailable_reason=group_diff_unavailable_reason,
    )
