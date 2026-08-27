"""T040 — EquivalenceResult enums (data-model.md §8)."""

from amayama_scraper.equivalence.types import (
    EquivalenceResult,
    ImageRelation,
    PartsRelation,
    SchemaRelation,
)


def test_parts_relation_has_three_values():
    assert {v.value for v in PartsRelation} == {"EXACT", "DIFFERENT", "UNKNOWN"}


def test_schema_relation_has_three_values():
    assert {v.value for v in SchemaRelation} == {"EXACT", "DIFFERENT", "UNKNOWN"}


def test_image_relation_has_five_values():
    assert {v.value for v in ImageRelation} == {
        "EXACT",
        "COMPLEMENTARY",
        "DIFFERENT",
        "NONE",
        "UNKNOWN",
    }


def test_equivalence_result_construction():
    result = EquivalenceResult(
        comparison_valid=True,
        parts_relation=PartsRelation.EXACT,
        schema_relation=SchemaRelation.EXACT,
        image_relation=ImageRelation.COMPLEMENTARY,
    )
    assert result.comparison_valid is True
    assert result.parts_relation is PartsRelation.EXACT
