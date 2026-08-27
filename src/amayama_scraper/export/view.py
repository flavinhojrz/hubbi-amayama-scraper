"""ExportView — contracts/export-boundary-contract.md.

Representação de domínio interna — nunca um schema do ecossistema Hubbi
(fora de escopo, FR-033). Nenhum dado é perdido na fronteira.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from amayama_scraper.assets.types import ResolvedImage
from amayama_scraper.domain.hierarchy import Category
from amayama_scraper.domain.identity import SpecIdentity
from amayama_scraper.snapshots.snapshot import SnapshotState


@dataclass(frozen=True, slots=True)
class ClusterInfo:
    cluster_key: str
    is_representative: bool
    representative_spec_ref: str


@dataclass(frozen=True, slots=True)
class SnapshotReference:
    snapshot_id: str
    state: SnapshotState
    collected_at: datetime
    parser_version: str
    normalizer_version: str
    fingerprint_version: str


@dataclass(frozen=True, slots=True)
class ExportView:
    spec_identity: SpecIdentity
    hierarchy: tuple[Category, ...]
    cluster: ClusterInfo | None
    resolved_image: ResolvedImage | None
    snapshot_reference: SnapshotReference
