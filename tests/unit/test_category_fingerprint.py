"""T118 — category_fingerprint(): multiset inclui grupos vazios, category_slug participa."""

from amayama_scraper.domain.hierarchy import Category, Group
from amayama_scraper.fingerprints.category import category_fingerprint


def test_empty_groups_are_included_in_the_multiset():
    c1 = Category(category_slug="engine", groups=(Group(group_id="1"),))
    c2 = Category(category_slug="engine", groups=())
    assert category_fingerprint(c1) != category_fingerprint(c2)


def test_category_slug_participates_in_the_fingerprint():
    c1 = Category(category_slug="engine", groups=(Group(group_id="1"),))
    c2 = Category(category_slug="gearbox", groups=(Group(group_id="1"),))
    assert category_fingerprint(c1) != category_fingerprint(c2)


def test_order_of_groups_does_not_matter():
    c1 = Category(category_slug="engine", groups=(Group("1"), Group("2")))
    c2 = Category(category_slug="engine", groups=(Group("2"), Group("1")))
    assert category_fingerprint(c1) == category_fingerprint(c2)
