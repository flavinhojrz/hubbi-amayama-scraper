"""build_export_view() — contracts/export-boundary-contract.md.

`spec_entry` do contrato é composto aqui como `(identity, hierarchy)` — os
dois dados já existem separadamente no domínio (não há um único tipo
"SpecEntry" agregado); nenhuma informação nova é inventada.
"""

from __future__ import annotations

from amayama_scraper.assets.types import ResolvedImage
from amayama_scraper.domain.hierarchy import Category
from amayama_scraper.domain.identity import SpecIdentity
from amayama_scraper.equivalence.cluster_types import EquivalenceClass
from amayama_scraper.export.view import ClusterInfo, ExportView, SnapshotReference
from amayama_scraper.snapshots.snapshot import SpecSnapshot


def build_export_view(
    *,
    identity: SpecIdentity,
    hierarchy: tuple[Category, ...],
    cluster: EquivalenceClass | None,
    resolved_image: ResolvedImage | None,
    snapshot: SpecSnapshot,
) -> ExportView:
    cluster_info = None
    if cluster is not None:
        cluster_info = ClusterInfo(
            cluster_key=cluster.cluster_key,
            is_representative=(snapshot.spec_identity_ref == cluster.representative_spec_ref),
            representative_spec_ref=cluster.representative_spec_ref,
        )

    return ExportView(
        spec_identity=identity,
        hierarchy=hierarchy,
        cluster=cluster_info,
        resolved_image=resolved_image,
        snapshot_reference=SnapshotReference(
            snapshot_id=snapshot.snapshot_id,
            state=snapshot.state,
            collected_at=snapshot.collected_at,
            parser_version=snapshot.parser_version,
            normalizer_version=snapshot.normalizer_version,
            fingerprint_version=snapshot.fingerprint_version,
        ),
    )
