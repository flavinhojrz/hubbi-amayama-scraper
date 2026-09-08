"""render_*_text() — apresentação humana, spec.md FR-002.

Puro: recebe os dataclasses de analysis/types.py, devolve str. Nenhuma
lógica de cálculo vive aqui — apenas formatação.
"""

from __future__ import annotations

from amayama_scraper.analysis.types import (
    DistributionStats,
    QualityReport,
    RedundancyClusterMember,
    RedundancyReport,
    ScopeSummary,
    SpecComparison,
)


def _fmt_dist(label: str, stats: DistributionStats) -> str:
    if stats.sample_size == 0:
        return f"  {label}: (sem specs com snapshot para calcular)"
    return (
        f"  {label}: min={stats.minimum} max={stats.maximum} "
        f"mean={stats.mean:.2f} median={stats.median:.2f} (n={stats.sample_size})"
    )


def render_summary_text(summary: ScopeSummary) -> str:
    lines = [
        f"Resumo geral — {summary.scope.label()}",
        f"  specs descobertas: {summary.specs_discovered}",
        f"  specs VALID + completas: {summary.specs_valid_complete}",
        f"  specs incompletas/problemáticas: {summary.specs_incomplete_or_problematic}",
        f"  categorias (soma por spec): {summary.categories_total}",
        f"  grupos (soma por spec): {summary.groups_total}",
        f"  schemas (soma por spec): {summary.schemas_total}",
        f"  ocorrências de peças (soma por spec): {summary.parts_total}",
        f"  specs com zero peças: {summary.specs_with_zero_parts}",
        f"  specs consideradas na distribuição (têm snapshot): "
        f"{summary.specs_considered_for_distribution}",
        _fmt_dist("grupos/spec", summary.groups_per_spec),
        _fmt_dist("schemas/spec", summary.schemas_per_spec),
        _fmt_dist("parts/spec", summary.parts_per_spec),
    ]
    return "\n".join(lines)


def render_quality_text(report: QualityReport) -> str:
    counts = report.counts_by_severity()
    lines = [
        f"Qualidade da coleta — {report.scope.label()}",
        f"  achados: ERROR={counts['ERROR']} WARNING={counts['WARNING']} INFO={counts['INFO']}",
    ]
    if not report.findings:
        lines.append("  nenhum achado.")
    for finding in report.findings:
        lines.append(f"  [{finding.severity.value}] {finding.code}: {finding.message}")
    return "\n".join(lines)


def _fmt_parts_count(value: int) -> str:
    """5432 -> "5.432" (separador de milhar por ponto, mesmo estilo do exemplo
    acordado com o PO) — puramente de formatação, não recalcula nada."""
    return f"{value:,}".replace(",", ".")


def _fmt_grade_configuration(member: RedundancyClusterMember) -> str:
    parts = [value for value in (member.grade, member.configuration) if value]
    return " / ".join(parts) if parts else "—"


def render_redundancy_text(report: RedundancyReport) -> str:
    lines = [
        f"Redundância — {report.scope.label()}",
        f"  specs consideradas (elegíveis para equivalência): {report.specs_considered}",
        f"  spec_parts_hash distintos: {report.distinct_spec_parts_hash}",
        f"  structure_hash distintos: {report.distinct_structure_hash}",
        f"  schema_semantic_hash distintos: {report.distinct_schema_semantic_hash}",
        f"  image_hash distintos: {report.distinct_image_hash}",
        f"  specs isoladas (sem duplicata): {report.isolated_spec_count}",
        f"  maior cluster: {report.largest_cluster_size}",
        f"  taxa de redução potencial: {report.potential_reduction_ratio:.2%}",
        f"  clusters redundantes (tamanho >= 2): {len(report.clusters)}",
    ]
    for cluster in report.clusters:
        lines.append(
            f"  Cluster — {cluster.size} specs (spec_parts_hash={cluster.spec_parts_hash[:16]}...)"
        )
        for member in cluster.members:
            lines.append(
                f"    {member.model_code} | catalog {member.amayama_catalog_id} | "
                f"{member.production_period_raw} | {_fmt_grade_configuration(member)} | "
                f"{_fmt_parts_count(member.parts_count)} parts | key={member.stable_key}"
            )
    return "\n".join(lines)


def render_comparison_text(comparison: SpecComparison) -> str:
    lines = [
        f"Comparação — {comparison.scope.label()}",
        f"  A: {comparison.display_key_a} ({comparison.stable_key_a})",
        f"  B: {comparison.display_key_b} ({comparison.stable_key_b})",
        f"  counts A: {comparison.counts_a}",
        f"  counts B: {comparison.counts_b}",
    ]
    if comparison.equivalence is not None:
        eq = comparison.equivalence
        lines.append(
            f"  equivalência: comparison_valid={eq.comparison_valid} "
            f"parts_relation={eq.parts_relation.value} "
            f"schema_relation={eq.schema_relation.value} "
            f"image_relation={eq.image_relation.value}"
        )
    else:
        lines.append(f"  equivalência: indisponível — {comparison.equivalence_unavailable_reason}")

    hc = comparison.hash_comparison
    lines.append(
        "  hashes: "
        f"structure_hash={hc.structure_hash.value} "
        f"spec_parts_hash={hc.spec_parts_hash.value} "
        f"schema_semantic_hash={hc.schema_semantic_hash.value} "
        f"image_hash={hc.image_hash.value}"
    )

    if comparison.group_diff is not None:
        diff = comparison.group_diff
        lines.append(f"  grupos só em A: {len(diff.only_in_a)}")
        lines.append(f"  grupos só em B: {len(diff.only_in_b)}")
        lines.append(f"  grupos compartilhados: {len(diff.shared)}")
    else:
        lines.append(f"  diff de grupos: indisponível — {comparison.group_diff_unavailable_reason}")

    parts_diff_status = "disponível" if comparison.parts_diff_available else "indisponível"
    lines.append(
        f"  diff de OEMs/peças: {parts_diff_status} — {comparison.parts_diff_unavailable_reason}"
    )
    return "\n".join(lines)
