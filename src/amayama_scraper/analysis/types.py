"""Tipos de dados puros para relatórios de análise — spec.md US1-US4, plan.md.

Nenhum tipo aqui é persistido; são projeções de leitura, construídas por
summary.py/quality.py/redundancy.py/comparison.py a partir de dados já
carregados de repositories/*.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from amayama_scraper.equivalence.types import EquivalenceResult


@dataclass(frozen=True, slots=True)
class ScopeIdentifier:
    manufacturer: str
    vehicle_model: str
    market: str

    def __post_init__(self) -> None:
        for field_name in ("manufacturer", "vehicle_model", "market"):
            value = getattr(self, field_name)
            if not value or not value.strip():
                raise ValueError(f"ScopeIdentifier.{field_name} must not be empty")

    def label(self) -> str:
        return f"{self.manufacturer} / {self.vehicle_model} / {self.market}"


@dataclass(frozen=True, slots=True)
class DistributionStats:
    """mín/máx/média/mediana sobre um conjunto de valores inteiros."""

    minimum: int
    maximum: int
    mean: float
    median: float
    sample_size: int

    @staticmethod
    def empty() -> DistributionStats:
        return DistributionStats(minimum=0, maximum=0, mean=0.0, median=0.0, sample_size=0)


@dataclass(frozen=True, slots=True)
class ScopeSummary:
    scope: ScopeIdentifier
    specs_discovered: int
    specs_valid_complete: int
    specs_incomplete_or_problematic: int
    categories_total: int
    groups_total: int
    schemas_total: int
    parts_total: int
    specs_with_zero_parts: int
    specs_considered_for_distribution: int
    groups_per_spec: DistributionStats
    schemas_per_spec: DistributionStats
    parts_per_spec: DistributionStats


class Severity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


@dataclass(frozen=True, slots=True)
class Finding:
    severity: Severity
    code: str
    spec_stable_key: str | None
    message: str
    details: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class QualityReport:
    scope: ScopeIdentifier
    findings: tuple[Finding, ...]

    def counts_by_severity(self) -> dict[str, int]:
        counts = {severity.value: 0 for severity in Severity}
        for finding in self.findings:
            counts[finding.severity.value] += 1
        return counts


@dataclass(frozen=True, slots=True)
class RedundancyClusterMember:
    """Uma spec dentro de um cluster de redundância, com metadados humanos —
    stable_key é preservado apenas como identificador secundário (ex.: para
    usar em `compare`), nunca como a informação principal exibida."""

    stable_key: str
    model_code: str
    amayama_catalog_id: str
    production_period_raw: str
    grade: str | None
    configuration: str | None
    parts_count: int


@dataclass(frozen=True, slots=True)
class RedundancyCluster:
    spec_parts_hash: str
    members: tuple[RedundancyClusterMember, ...]

    @property
    def size(self) -> int:
        return len(self.members)


@dataclass(frozen=True, slots=True)
class RedundancyReport:
    scope: ScopeIdentifier
    specs_considered: int
    distinct_spec_parts_hash: int
    distinct_structure_hash: int
    distinct_schema_semantic_hash: int
    distinct_image_hash: int
    clusters: tuple[RedundancyCluster, ...]
    isolated_spec_count: int
    largest_cluster_size: int
    potential_reduction_ratio: float


@dataclass(frozen=True, slots=True)
class GroupSetDiff:
    only_in_a: frozenset[tuple[str, str]]
    only_in_b: frozenset[tuple[str, str]]
    shared: frozenset[tuple[str, str]]


class HashComparisonState(StrEnum):
    """Estado literal de um único par de hashes — diagnóstico direto, distinto
    de EquivalenceResult (que carrega semântica de domínio como COMPLEMENTARY).
    Codex finding #3 (003-corpus-analysis-tool)."""

    EQUAL = "EQUAL"
    DIFFERENT = "DIFFERENT"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class HashComparison:
    """Comparação literal dos 4 fingerprints independentes lado a lado.

    UNAVAILABLE cobre tanto "sem snapshot"/"escopo ou versão incompatível"
    (todo o registro) quanto "hash NULL nesse spec específico" (só o campo
    afetado) — nunca uma igualdade/diferença inventada nesses casos.
    """

    structure_hash: HashComparisonState
    spec_parts_hash: HashComparisonState
    schema_semantic_hash: HashComparisonState
    image_hash: HashComparisonState


@dataclass(frozen=True, slots=True)
class SpecComparison:
    scope: ScopeIdentifier
    stable_key_a: str
    stable_key_b: str
    display_key_a: str
    display_key_b: str
    counts_a: dict[str, int] | None
    counts_b: dict[str, int] | None
    equivalence: EquivalenceResult | None
    equivalence_unavailable_reason: str | None
    hash_comparison: HashComparison
    group_diff: GroupSetDiff | None
    group_diff_unavailable_reason: str | None
    parts_diff_available: bool = False
    parts_diff_unavailable_reason: str = (
        "diff de OEMs/peças individuais exige reprocessar raw HTML "
        "(não existe tabela relacional de parts) — fora de escopo desta ferramenta"
    )
