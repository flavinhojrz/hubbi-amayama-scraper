"""T147 — EquivalenceClass agrupa membros com mesmo cluster_key, preserva member_spec_refs."""

from amayama_scraper.equivalence.cluster import build_equivalence_class, cluster_key

SCOPE = "AMAYAMA:VOLKSWAGEN:AMAROK:AMA-BR"


def test_build_equivalence_class_uses_documented_cluster_key():
    result = build_equivalence_class(
        scope=SCOPE,
        normalizer_version="amayama-normalizer-v1",
        fingerprint_version="amayama-fingerprint-v1",
        spec_parts_hash="x" * 64,
        member_spec_refs=("spec-a", "spec-b"),
        representative_spec_ref="spec-a",
    )
    expected_key = cluster_key(
        scope=SCOPE,
        normalizer_version="amayama-normalizer-v1",
        fingerprint_version="amayama-fingerprint-v1",
        spec_parts_hash="x" * 64,
    )
    assert result.cluster_key == expected_key
    assert result.member_spec_refs == ("spec-a", "spec-b")
    assert result.representative_spec_ref == "spec-a"


def test_identity_never_erased_all_members_preserved():
    result = build_equivalence_class(
        scope=SCOPE,
        normalizer_version="v1",
        fingerprint_version="v1",
        spec_parts_hash="x" * 64,
        member_spec_refs=("spec-a", "spec-b", "spec-c"),
        representative_spec_ref="spec-b",
    )
    assert "spec-a" in result.member_spec_refs
    assert "spec-b" in result.member_spec_refs
    assert "spec-c" in result.member_spec_refs
