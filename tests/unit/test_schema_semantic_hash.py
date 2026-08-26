"""T124 — schema_semantic_hash(): multiset de schema_id, independente de spec_parts_hash."""

from amayama_scraper.domain.hierarchy import Category, Group, Schema
from amayama_scraper.domain.part import Part
from amayama_scraper.fingerprints.schema_semantic import schema_semantic_hash
from amayama_scraper.fingerprints.spec import spec_parts_hash


def test_part_content_change_does_not_affect_schema_semantic_hash():
    t1 = (
        Category("engine", groups=(Group("1", schemas=(Schema("s1", parts=(Part("s1", "A"),)),)),)),
    )
    t2 = (
        Category("engine", groups=(Group("1", schemas=(Schema("s1", parts=(Part("s1", "B"),)),)),)),
    )
    assert schema_semantic_hash(t1) == schema_semantic_hash(t2)
    assert spec_parts_hash(t1) != spec_parts_hash(t2)


def test_different_schema_id_changes_hash():
    t1 = (Category("engine", groups=(Group("1", schemas=(Schema("s1"),)),)),)
    t2 = (Category("engine", groups=(Group("1", schemas=(Schema("s2"),)),)),)
    assert schema_semantic_hash(t1) != schema_semantic_hash(t2)
