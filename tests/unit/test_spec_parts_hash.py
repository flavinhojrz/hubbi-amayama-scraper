"""T120 — spec_parts_hash(): multiset de category_fingerprint; identidade nunca entra."""

from amayama_scraper.domain.hierarchy import Category, Group, Schema
from amayama_scraper.domain.part import Part
from amayama_scraper.fingerprints.spec import spec_parts_hash


def _tree() -> tuple[Category, ...]:
    return (
        Category(
            category_slug="engine",
            groups=(
                Group(
                    group_id="1",
                    schemas=(Schema("s1", parts=(Part(schema_id="s1", position_pnc="A"),)),),
                ),
            ),
        ),
    )


def test_deterministic():
    tree = _tree()
    assert spec_parts_hash(tree) == spec_parts_hash(tree)


def test_order_of_categories_does_not_matter():
    t1 = (
        Category("engine", groups=(Group("1"),)),
        Category("gearbox", groups=(Group("2"),)),
    )
    t2 = (
        Category("gearbox", groups=(Group("2"),)),
        Category("engine", groups=(Group("1"),)),
    )
    assert spec_parts_hash(t1) == spec_parts_hash(t2)


def test_content_change_changes_the_hash():
    t1 = _tree()
    t2 = (
        Category(
            category_slug="engine",
            groups=(
                Group(
                    group_id="1",
                    schemas=(Schema("s1", parts=(Part(schema_id="s1", position_pnc="B"),)),),
                ),
            ),
        ),
    )
    assert spec_parts_hash(t1) != spec_parts_hash(t2)


def test_empty_tree_produces_a_valid_hash():
    assert len(spec_parts_hash(())) == 64
