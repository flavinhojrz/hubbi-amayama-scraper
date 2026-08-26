"""T122 — structure_hash(): multiset de categories/groups/schemas, sem conteúdo de parts."""

from amayama_scraper.domain.hierarchy import Category, Group, Schema
from amayama_scraper.domain.part import Part
from amayama_scraper.fingerprints.structure import structure_hash


def test_content_change_alone_does_not_change_structure_hash():
    t1 = (
        Category(
            "engine",
            groups=(Group("1", schemas=(Schema("s1", parts=(Part("s1", "A"),)),)),),
        ),
    )
    t2 = (
        Category(
            "engine",
            groups=(Group("1", schemas=(Schema("s1", parts=(Part("s1", "B"),)),)),),
        ),
    )
    assert structure_hash(t1) == structure_hash(t2)


def test_structural_change_changes_structure_hash():
    t1 = (Category("engine", groups=(Group("1"),)),)
    t2 = (Category("engine", groups=(Group("1"), Group("2"))),)
    assert structure_hash(t1) != structure_hash(t2)


def test_order_independent():
    t1 = (Category("engine", groups=(Group("1"),)), Category("gearbox", groups=(Group("2"),)))
    t2 = (Category("gearbox", groups=(Group("2"),)), Category("engine", groups=(Group("1"),)))
    assert structure_hash(t1) == structure_hash(t2)
