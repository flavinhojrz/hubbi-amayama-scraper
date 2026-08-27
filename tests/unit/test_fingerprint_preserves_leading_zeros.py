"""T129 — group_id com zeros à esquerda é preservado (nunca convertido para int)."""

from amayama_scraper.domain.hierarchy import Group
from amayama_scraper.fingerprints.group import group_fingerprint


def test_leading_zeros_group_id_differs_from_stripped_form():
    g1 = Group(group_id="010")
    g2 = Group(group_id="10")
    assert group_fingerprint(g1) != group_fingerprint(g2)
