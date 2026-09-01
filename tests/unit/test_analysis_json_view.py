"""T020 — to_json_dict()-style functions: mesma entrada -> mesma serialização (determinismo)."""

import json

from amayama_scraper.analysis.json_view import (
    quality_report_to_dict,
    redundancy_report_to_dict,
    scope_summary_to_dict,
    spec_comparison_to_dict,
)
from amayama_scraper.analysis.types import (
    DistributionStats,
    Finding,
    GroupSetDiff,
    HashComparison,
    HashComparisonState,
    QualityReport,
    RedundancyCluster,
    RedundancyClusterMember,
    RedundancyReport,
    ScopeIdentifier,
    ScopeSummary,
    Severity,
    SpecComparison,
)
from amayama_scraper.equivalence.types import (
    EquivalenceResult,
    ImageRelation,
    PartsRelation,
    SchemaRelation,
)

SCOPE = ScopeIdentifier(manufacturer="VOLKSWAGEN", vehicle_model="AMAROK", market="AMA-BR")
DIST = DistributionStats(minimum=1, maximum=5, mean=3.0, median=3.0, sample_size=2)


def _dumps(payload: dict) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def test_scope_summary_serialization_is_deterministic():
    summary = ScopeSummary(
        scope=SCOPE,
        specs_discovered=2,
        specs_valid_complete=2,
        specs_incomplete_or_problematic=0,
        categories_total=2,
        groups_total=10,
        schemas_total=40,
        parts_total=500,
        specs_with_zero_parts=0,
        specs_considered_for_distribution=2,
        groups_per_spec=DIST,
        schemas_per_spec=DIST,
        parts_per_spec=DIST,
    )

    first = _dumps(scope_summary_to_dict(summary))
    second = _dumps(scope_summary_to_dict(summary))

    assert first == second
    assert json.loads(first)["specs_discovered"] == 2


def test_quality_report_serialization_is_deterministic():
    report = QualityReport(
        scope=SCOPE,
        findings=(
            Finding(
                severity=Severity.WARNING,
                code="SNAPSHOT_NOT_VALID",
                spec_stable_key="abc",
                message="msg",
                details={"state": "STALE"},
            ),
        ),
    )

    assert _dumps(quality_report_to_dict(report)) == _dumps(quality_report_to_dict(report))


def test_redundancy_report_serialization_includes_human_readable_member_fields():
    member_z = RedundancyClusterMember(
        stable_key="z",
        model_code="ZZZ1",
        amayama_catalog_id="900",
        production_period_raw="2016.06-2019.08",
        grade="Highline",
        configuration="4Motion",
        parts_count=5432,
    )
    member_a = RedundancyClusterMember(
        stable_key="a",
        model_code="AAA1",
        amayama_catalog_id="100",
        production_period_raw="2016.06-2019.08",
        grade=None,
        configuration=None,
        parts_count=100,
    )
    report = RedundancyReport(
        scope=SCOPE,
        specs_considered=2,
        distinct_spec_parts_hash=1,
        distinct_structure_hash=2,
        distinct_schema_semantic_hash=2,
        distinct_image_hash=2,
        clusters=(RedundancyCluster(spec_parts_hash="h" * 64, members=(member_z, member_a)),),
        isolated_spec_count=0,
        largest_cluster_size=2,
        potential_reduction_ratio=0.5,
    )

    payload = redundancy_report_to_dict(report)
    members_payload = payload["clusters"][0]["members"]
    assert members_payload == [
        {
            "stable_key": "z",
            "model_code": "ZZZ1",
            "amayama_catalog_id": "900",
            "production_period_raw": "2016.06-2019.08",
            "grade": "Highline",
            "configuration": "4Motion",
            "parts_count": 5432,
        },
        {
            "stable_key": "a",
            "model_code": "AAA1",
            "amayama_catalog_id": "100",
            "production_period_raw": "2016.06-2019.08",
            "grade": None,
            "configuration": None,
            "parts_count": 100,
        },
    ]
    assert _dumps(payload) == _dumps(redundancy_report_to_dict(report))
    assert _dumps(payload) == _dumps(redundancy_report_to_dict(report))


def test_spec_comparison_serialization_sorts_group_diff_sets():
    comparison = SpecComparison(
        scope=SCOPE,
        stable_key_a="key-a",
        stable_key_b="key-b",
        display_key_a="A",
        display_key_b="B",
        counts_a={"groups": 2},
        counts_b={"groups": 3},
        equivalence=EquivalenceResult(
            comparison_valid=True,
            parts_relation=PartsRelation.EXACT,
            schema_relation=SchemaRelation.EXACT,
            image_relation=ImageRelation.NONE,
        ),
        equivalence_unavailable_reason=None,
        hash_comparison=HashComparison(
            structure_hash=HashComparisonState.EQUAL,
            spec_parts_hash=HashComparisonState.EQUAL,
            schema_semantic_hash=HashComparisonState.DIFFERENT,
            image_hash=HashComparisonState.UNAVAILABLE,
        ),
        group_diff=GroupSetDiff(
            only_in_a=frozenset({("engine", "2"), ("engine", "1")}),
            only_in_b=frozenset(),
            shared=frozenset({("engine", "3")}),
        ),
        group_diff_unavailable_reason=None,
    )

    payload = spec_comparison_to_dict(comparison)
    assert payload["group_diff"]["only_in_a"] == ["engine/1", "engine/2"]
    assert payload["hash_comparison"] == {
        "structure_hash": "EQUAL",
        "spec_parts_hash": "EQUAL",
        "schema_semantic_hash": "DIFFERENT",
        "image_hash": "UNAVAILABLE",
    }
    first = _dumps(payload)
    second = _dumps(spec_comparison_to_dict(comparison))
    assert first == second
