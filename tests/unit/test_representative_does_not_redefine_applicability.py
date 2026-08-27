"""T155 — representante nunca redefine aplicabilidade (não-representantes seguem membros)."""

from amayama_scraper.equivalence.cluster import build_equivalence_class

SCOPE = "AMAYAMA:VOLKSWAGEN:AMAROK:AMA-BR"


def test_non_representative_members_remain_queryable():
    result = build_equivalence_class(
        scope=SCOPE,
        normalizer_version="v1",
        fingerprint_version="v1",
        spec_parts_hash="x" * 64,
        member_spec_refs=("spec-a", "spec-b", "spec-c"),
        representative_spec_ref="spec-b",
    )
    non_representatives = [
        m for m in result.member_spec_refs if m != result.representative_spec_ref
    ]
    assert non_representatives == ["spec-a", "spec-c"]
    # non-representatives remain valid members of the class — never dropped
    assert set(non_representatives) <= set(result.member_spec_refs)
