"""T017 — Category/Group/Schema invariants (data-model.md §2)."""

import pytest

from amayama_scraper.domain.hierarchy import Category, DuplicateGroupIdError, Group, Schema


def test_group_id_preserved_as_string_with_leading_zeros():
    group = Group(group_id="007")
    assert group.group_id == "007"
    assert isinstance(group.group_id, str)


def test_empty_group_is_valid():
    group = Group(group_id="1")
    assert group.schemas == ()


def test_category_with_empty_group_is_valid():
    category = Category(category_slug="front-axle-steering", groups=(Group(group_id="1"),))
    assert len(category.groups) == 1
    assert category.groups[0].schemas == ()


def test_duplicate_group_id_within_same_category_raises():
    with pytest.raises(DuplicateGroupIdError):
        Category(
            category_slug="front-axle-steering",
            groups=(Group(group_id="1"), Group(group_id="1")),
        )


def test_same_group_id_in_different_categories_is_allowed():
    a = Category(category_slug="front-axle-steering", groups=(Group(group_id="1"),))
    b = Category(category_slug="rear-axle", groups=(Group(group_id="1"),))
    assert a.groups[0].group_id == b.groups[0].group_id  # not an error across categories


def test_schema_requires_schema_id():
    with pytest.raises(ValueError):
        Schema(schema_id="")


def test_schema_holds_parts_tuple():
    schema = Schema(schema_id="SCH-1")
    assert schema.parts == ()
