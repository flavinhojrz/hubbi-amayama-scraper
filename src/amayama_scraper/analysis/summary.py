"""build_scope_summary() — spec.md US1, plan.md.

Puro: opera sobre SpecIdentity/SpecSnapshot já carregados, nunca abre conexão.
"""

from __future__ import annotations

import statistics

from amayama_scraper.analysis.types import DistributionStats, ScopeIdentifier, ScopeSummary
from amayama_scraper.domain.identity import SpecIdentity
from amayama_scraper.snapshots.snapshot import SnapshotState, SpecSnapshot


def _distribution(values: list[int]) -> DistributionStats:
    if not values:
        return DistributionStats.empty()
    return DistributionStats(
        minimum=min(values),
        maximum=max(values),
        mean=statistics.mean(values),
        median=statistics.median(values),
        sample_size=len(values),
    )


def build_scope_summary(
    scope: ScopeIdentifier,
    specs: list[SpecIdentity],
    latest_snapshot_by_spec: dict[str, SpecSnapshot],
) -> ScopeSummary:
    """counts_json de cada spec é somado (DEC-002, spec.md) — não deduplicado.

    Distribuições (DEC-003, spec.md) só consideram specs com pelo menos um
    snapshot — uma spec sem snapshot entra em specs_discovered/problemático,
    mas não em specs_considered_for_distribution.
    """
    specs_discovered = len(specs)
    specs_valid_complete = 0
    categories_total = 0
    groups_total = 0
    schemas_total = 0
    parts_total = 0
    specs_with_zero_parts = 0
    groups_values: list[int] = []
    schemas_values: list[int] = []
    parts_values: list[int] = []

    for spec in specs:
        snapshot = latest_snapshot_by_spec.get(spec.stable_key())
        if snapshot is None:
            continue

        if snapshot.state is SnapshotState.VALID and snapshot.collection_complete:
            specs_valid_complete += 1

        counts = snapshot.counts
        categories = counts.get("categories", 0)
        groups = counts.get("groups", 0)
        schemas = counts.get("schemas", 0)
        parts = counts.get("parts", 0)

        categories_total += categories
        groups_total += groups
        schemas_total += schemas
        parts_total += parts
        if parts == 0:
            specs_with_zero_parts += 1

        groups_values.append(groups)
        schemas_values.append(schemas)
        parts_values.append(parts)

    return ScopeSummary(
        scope=scope,
        specs_discovered=specs_discovered,
        specs_valid_complete=specs_valid_complete,
        specs_incomplete_or_problematic=specs_discovered - specs_valid_complete,
        categories_total=categories_total,
        groups_total=groups_total,
        schemas_total=schemas_total,
        parts_total=parts_total,
        specs_with_zero_parts=specs_with_zero_parts,
        specs_considered_for_distribution=len(groups_values),
        groups_per_spec=_distribution(groups_values),
        schemas_per_spec=_distribution(schemas_values),
        parts_per_spec=_distribution(parts_values),
    )
