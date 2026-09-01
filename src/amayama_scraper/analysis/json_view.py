"""to_json_dict()-style functions — apresentação JSON, spec.md FR-002.

Puro: dict/list apenas com tipos JSON-nativos, coleções sempre ordenadas
para que a mesma entrada produza sempre a mesma serialização (determinismo).
O chamador (cli/analyze.py) faz `json.dumps(..., sort_keys=True)` por cima.
"""

from __future__ import annotations

from amayama_scraper.analysis.types import (
    DistributionStats,
    QualityReport,
    RedundancyReport,
    ScopeIdentifier,
    ScopeSummary,
    SpecComparison,
)


def _scope_dict(scope: ScopeIdentifier) -> dict[str, object]:
    return {
        "manufacturer": scope.manufacturer,
        "vehicle_model": scope.vehicle_model,
        "market": scope.market,
        "label": scope.label(),
    }


def _distribution_dict(stats: DistributionStats) -> dict[str, object]:
    return {
        "min": stats.minimum,
        "max": stats.maximum,
        "mean": stats.mean,
        "median": stats.median,
        "sample_size": stats.sample_size,
    }


def scope_summary_to_dict(summary: ScopeSummary) -> dict[str, object]:
    return {
        "scope": _scope_dict(summary.scope),
        "specs_discovered": summary.specs_discovered,
        "specs_valid_complete": summary.specs_valid_complete,
        "specs_incomplete_or_problematic": summary.specs_incomplete_or_problematic,
        "categories_total": summary.categories_total,
        "groups_total": summary.groups_total,
        "schemas_total": summary.schemas_total,
        "parts_total": summary.parts_total,
        "specs_with_zero_parts": summary.specs_with_zero_parts,
        "specs_considered_for_distribution": summary.specs_considered_for_distribution,
        "groups_per_spec": _distribution_dict(summary.groups_per_spec),
        "schemas_per_spec": _distribution_dict(summary.schemas_per_spec),
        "parts_per_spec": _distribution_dict(summary.parts_per_spec),
    }


def quality_report_to_dict(report: QualityReport) -> dict[str, object]:
    return {
        "scope": _scope_dict(report.scope),
        "counts_by_severity": report.counts_by_severity(),
        "findings": [
            {
                "severity": finding.severity.value,
                "code": finding.code,
                "spec_stable_key": finding.spec_stable_key,
                "message": finding.message,
                "details": finding.details,
            }
            for finding in report.findings
        ],
    }


def redundancy_report_to_dict(report: RedundancyReport) -> dict[str, object]:
    return {
        "scope": _scope_dict(report.scope),
        "specs_considered": report.specs_considered,
        "distinct_spec_parts_hash": report.distinct_spec_parts_hash,
        "distinct_structure_hash": report.distinct_structure_hash,
        "distinct_schema_semantic_hash": report.distinct_schema_semantic_hash,
        "distinct_image_hash": report.distinct_image_hash,
        "isolated_spec_count": report.isolated_spec_count,
        "largest_cluster_size": report.largest_cluster_size,
        "potential_reduction_ratio": report.potential_reduction_ratio,
        "clusters": [
            {
                "spec_parts_hash": cluster.spec_parts_hash,
                "size": cluster.size,
                "members": [
                    {
                        "stable_key": member.stable_key,
                        "model_code": member.model_code,
                        "amayama_catalog_id": member.amayama_catalog_id,
                        "production_period_raw": member.production_period_raw,
                        "grade": member.grade,
                        "configuration": member.configuration,
                        "parts_count": member.parts_count,
                    }
                    for member in cluster.members
                ],
            }
            for cluster in report.clusters
        ],
    }


def spec_comparison_to_dict(comparison: SpecComparison) -> dict[str, object]:
    equivalence = comparison.equivalence
    group_diff = comparison.group_diff
    return {
        "scope": _scope_dict(comparison.scope),
        "spec_a": {
            "stable_key": comparison.stable_key_a,
            "display_key": comparison.display_key_a,
            "counts": comparison.counts_a,
        },
        "spec_b": {
            "stable_key": comparison.stable_key_b,
            "display_key": comparison.display_key_b,
            "counts": comparison.counts_b,
        },
        "equivalence": (
            {
                "comparison_valid": equivalence.comparison_valid,
                "parts_relation": equivalence.parts_relation.value,
                "schema_relation": equivalence.schema_relation.value,
                "image_relation": equivalence.image_relation.value,
            }
            if equivalence is not None
            else None
        ),
        "equivalence_unavailable_reason": comparison.equivalence_unavailable_reason,
        "hash_comparison": {
            "structure_hash": comparison.hash_comparison.structure_hash.value,
            "spec_parts_hash": comparison.hash_comparison.spec_parts_hash.value,
            "schema_semantic_hash": comparison.hash_comparison.schema_semantic_hash.value,
            "image_hash": comparison.hash_comparison.image_hash.value,
        },
        "group_diff": (
            {
                "only_in_a": sorted(f"{c}/{g}" for c, g in group_diff.only_in_a),
                "only_in_b": sorted(f"{c}/{g}" for c, g in group_diff.only_in_b),
                "shared": sorted(f"{c}/{g}" for c, g in group_diff.shared),
            }
            if group_diff is not None
            else None
        ),
        "group_diff_unavailable_reason": comparison.group_diff_unavailable_reason,
        "parts_diff_available": comparison.parts_diff_available,
        "parts_diff_unavailable_reason": comparison.parts_diff_unavailable_reason,
    }
