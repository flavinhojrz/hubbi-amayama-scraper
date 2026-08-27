"""T116 — group_fingerprint(): multiset ordem-irrelevante/duplicata-sensível, grupo vazio válido."""

from amayama_scraper.domain.hierarchy import Group, Schema
from amayama_scraper.domain.part import Part
from amayama_scraper.fingerprints.group import group_fingerprint


def _part(pnc: str, schema_id: str = "1") -> Part:
    return Part(schema_id=schema_id, position_pnc=pnc, oem_code=pnc)


def test_empty_group_produces_a_valid_fingerprint():
    group = Group(group_id="407")
    assert isinstance(group_fingerprint(group), str)
    assert len(group_fingerprint(group)) == 64


def test_order_of_schemas_and_parts_does_not_matter():
    g1 = Group(
        group_id="407",
        schemas=(
            Schema("1", parts=(_part("A"), _part("B"))),
            Schema("2", parts=(_part("C"),)),
        ),
    )
    g2 = Group(
        group_id="407",
        schemas=(
            Schema("2", parts=(_part("C"),)),
            Schema("1", parts=(_part("B"), _part("A"))),
        ),
    )
    assert group_fingerprint(g1) == group_fingerprint(g2)


def test_duplicate_parts_change_the_fingerprint():
    g1 = Group(group_id="407", schemas=(Schema("1", parts=(_part("A"),)),))
    g2 = Group(group_id="407", schemas=(Schema("1", parts=(_part("A"), _part("A"))),))
    assert group_fingerprint(g1) != group_fingerprint(g2)


def test_different_group_id_changes_fingerprint_even_with_same_parts():
    g1 = Group(group_id="407", schemas=(Schema("1", parts=(_part("A"),)),))
    g2 = Group(group_id="409", schemas=(Schema("1", parts=(_part("A"),)),))
    assert group_fingerprint(g1) != group_fingerprint(g2)
