"""build_redundancy_report() — spec.md US3, plan.md.

Puro. Reaproveita equivalence.cluster.cluster_key() (Constitution §9) — nunca
reimplementa comparação de hash. Estritamente informativo: nenhuma fusão,
nenhuma escrita em cluster_assignment.
"""

from __future__ import annotations

from collections import defaultdict

from amayama_scraper.analysis.types import (
    RedundancyCluster,
    RedundancyClusterMember,
    RedundancyReport,
    ScopeIdentifier,
)
from amayama_scraper.domain.identity import SpecIdentity
from amayama_scraper.equivalence.cluster import cluster_key
from amayama_scraper.fingerprints.types import UNAVAILABLE_HASH
from amayama_scraper.snapshots.snapshot import SnapshotState, SpecSnapshot

_ELIGIBLE_STATES = frozenset({SnapshotState.VALID, SnapshotState.STALE})
_HASH_FIELDS = ("structure_hash", "spec_parts_hash", "schema_semantic_hash", "image_hash")


def _equivalence_scope(source: str, scope: ScopeIdentifier) -> str:
    """Reproduz o formato normativo de checkpoint.collection_run.FIXED_SCOPE
    ("AMAYAMA:VOLKSWAGEN:AMAROK:AMA-BR") a partir dos campos de identidade já
    conhecidos — SpecSnapshot não carrega scope (equivalence/validity.py),
    então o chamador sempre precisa construí-lo; esta é a mesma construção,
    generalizada para qualquer (source, manufacturer, vehicle_model, market)."""
    return (
        f"{source.strip().upper()}:{scope.manufacturer.strip().upper()}:"
        f"{scope.vehicle_model.strip().upper()}:{scope.market.strip().upper()}"
    )


def _is_eligible(snapshot: SpecSnapshot) -> bool:
    """Constitution §11 — INCOMPLETE/INVALID não participam de equivalência.

    Também exclui snapshots com qualquer fingerprint indisponível (hash NULL
    no banco, representado por UNAVAILABLE_HASH) — nunca agrupado como
    equivalência técnica (Codex finding #5, 003-corpus-analysis-tool)."""
    if not (snapshot.collection_complete and snapshot.state in _ELIGIBLE_STATES):
        return False
    return all(getattr(snapshot, field) != UNAVAILABLE_HASH for field in _HASH_FIELDS)


def build_redundancy_report(
    scope: ScopeIdentifier,
    specs: list[SpecIdentity],
    latest_snapshot_by_spec: dict[str, SpecSnapshot],
) -> RedundancyReport:
    eligible: list[tuple[SpecIdentity, SpecSnapshot]] = []
    for spec in specs:
        snapshot = latest_snapshot_by_spec.get(spec.stable_key())
        if snapshot is not None and _is_eligible(snapshot):
            eligible.append((spec, snapshot))

    specs_considered = len(eligible)

    clusters_by_key: dict[str, list[RedundancyClusterMember]] = defaultdict(list)
    spec_parts_hash_by_cluster_key: dict[str, str] = {}
    distinct_structure = set()
    distinct_schema_semantic = set()
    distinct_image = set()

    for spec, snapshot in eligible:
        scope_str = _equivalence_scope(spec.source, scope)
        key = cluster_key(
            scope=scope_str,
            normalizer_version=snapshot.normalizer_version,
            fingerprint_version=snapshot.fingerprint_version,
            spec_parts_hash=snapshot.spec_parts_hash,
        )
        # Metadados humanos já disponíveis em SpecIdentity/SpecSnapshot — nunca
        # exige nova leitura de repositório (analysis/ permanece puro).
        clusters_by_key[key].append(
            RedundancyClusterMember(
                stable_key=spec.stable_key(),
                model_code=spec.model_code,
                amayama_catalog_id=spec.amayama_catalog_id,
                production_period_raw=spec.production_period_raw,
                grade=spec.grade,
                configuration=spec.configuration,
                parts_count=snapshot.counts.get("parts", 0),
            )
        )
        spec_parts_hash_by_cluster_key[key] = snapshot.spec_parts_hash
        distinct_structure.add(snapshot.structure_hash)
        distinct_schema_semantic.add(snapshot.schema_semantic_hash)
        distinct_image.add(snapshot.image_hash)

    distinct_spec_parts_hash = len(clusters_by_key)

    redundant_clusters = sorted(
        (
            RedundancyCluster(
                spec_parts_hash=spec_parts_hash_by_cluster_key[key],
                # Determinístico: model_code -> amayama_catalog_id -> stable_key
                # (desempate final), nunca depende de ordem de iteração de dict.
                members=tuple(
                    sorted(
                        members,
                        key=lambda m: (m.model_code, m.amayama_catalog_id, m.stable_key),
                    )
                ),
            )
            for key, members in clusters_by_key.items()
            if len(members) >= 2
        ),
        key=lambda c: (-c.size, c.spec_parts_hash),
    )
    isolated_spec_count = sum(1 for members in clusters_by_key.values() if len(members) == 1)
    largest_cluster_size = max((c.size for c in redundant_clusters), default=0)
    reduction_ratio = (
        (specs_considered - distinct_spec_parts_hash) / specs_considered
        if specs_considered > 0
        else 0.0
    )

    return RedundancyReport(
        scope=scope,
        specs_considered=specs_considered,
        distinct_spec_parts_hash=distinct_spec_parts_hash,
        distinct_structure_hash=len(distinct_structure),
        distinct_schema_semantic_hash=len(distinct_schema_semantic),
        distinct_image_hash=len(distinct_image),
        clusters=tuple(redundant_clusters),
        isolated_spec_count=isolated_spec_count,
        largest_cluster_size=largest_cluster_size,
        potential_reduction_ratio=reduction_ratio,
    )
