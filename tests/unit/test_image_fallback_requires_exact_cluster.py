"""T160 — fallback só ocorre dentro de cluster com parts_relation == EXACT comprovado (FR-023).

A "prova" do EXACT já aconteceu na Phase 8 (build_equivalence_class só
agrupa specs com o mesmo spec_parts_hash) — resolve_image() exige que o
`spec_identity_ref` já seja um `member_spec_refs` do cluster passado;
nenhum fallback é considerado sem esse cluster já resolvido.
"""

from amayama_scraper.assets.fallback import resolve_image
from amayama_scraper.equivalence.cluster import build_equivalence_class

SCOPE = "AMAYAMA:VOLKSWAGEN:AMAROK:AMA-BR"


def _cluster(members: tuple[str, ...]) -> object:
    return build_equivalence_class(
        scope=SCOPE,
        normalizer_version="v1",
        fingerprint_version="v1",
        spec_parts_hash="x" * 64,
        member_spec_refs=members,
        representative_spec_ref=members[0],
    )


def test_fallback_uses_own_image_from_proven_cluster_member():
    cluster = _cluster(("spec-a", "spec-b"))
    result = resolve_image(
        spec_identity_ref="spec-a",
        own_image_refs=(),
        cluster=cluster,
        member_own_image_refs={"spec-b": ("https://x/b.jpg",)},
    )
    assert result is not None
    assert result.is_fallback is True
    assert result.origin_spec_ref == "spec-b"
    assert result.resolved_within_cluster_key == cluster.cluster_key  # type: ignore[attr-defined]


def test_no_cluster_no_fallback():
    result = resolve_image(
        spec_identity_ref="spec-a",
        own_image_refs=(),
        cluster=None,
        member_own_image_refs={"spec-b": ("https://x/b.jpg",)},
    )
    assert result is None
