"""T228 — revalidação incremental usa structure_hash primeiro, localiza divergência
hierárquica antes de recomputar tudo (FR-032, contracts/equivalence-contracts.md)."""

from amayama_scraper.domain.hierarchy import Category, Group, Schema
from amayama_scraper.domain.part import Part
from amayama_scraper.snapshots.revalidation import revalidate_spec_entry


def _tree(part_value: str, extra_group: bool = False) -> tuple[Category, ...]:
    groups = [Group("1", schemas=(Schema("s1", parts=(Part("s1", "A", oem_code=part_value),)),))]
    if extra_group:
        groups.append(Group("2", schemas=(Schema("s2", parts=(Part("s2", "B"),)),)))
    return (Category("engine", groups=tuple(groups)),)


def test_no_change_reports_nothing_stale():
    tree = _tree("X")
    report = revalidate_spec_entry(tree, tree)
    assert report.structure_changed is False
    assert report.content_changed is False
    assert report.is_stale is False
    assert report.divergent_category_slugs == ()


def test_content_only_change_reports_content_changed_but_not_structure():
    previous = _tree("X")
    current = _tree("Y")
    report = revalidate_spec_entry(previous, current)
    assert report.structure_changed is False
    assert report.content_changed is True
    assert report.is_stale is True
    assert report.divergent_category_slugs == ("engine",)
    assert report.divergent_group_keys == (("engine", "1"),)


def test_structural_change_reports_structure_changed_and_localizes_category():
    previous = _tree("X")
    current = _tree("X", extra_group=True)
    report = revalidate_spec_entry(previous, current)
    assert report.structure_changed is True
    assert report.divergent_category_slugs == ("engine",)
    assert ("engine", "2") in report.divergent_group_keys
    assert ("engine", "1") not in report.divergent_group_keys  # unchanged group not flagged


def test_unaffected_category_is_never_flagged():
    engine_group_a = Group("1", schemas=(Schema("s1", parts=(Part("s1", "A"),)),))
    engine_group_changed = Group("1", schemas=(Schema("s1", parts=(Part("s1", "CHANGED"),)),))
    gearbox_group = Group("2", schemas=(Schema("s2", parts=(Part("s2", "B"),)),))

    previous = (
        Category("engine", groups=(engine_group_a,)),
        Category("gearbox", groups=(gearbox_group,)),
    )
    current = (
        Category("engine", groups=(engine_group_changed,)),
        Category("gearbox", groups=(gearbox_group,)),
    )
    report = revalidate_spec_entry(previous, current)
    assert report.divergent_category_slugs == ("engine",)
    assert "gearbox" not in report.divergent_category_slugs
