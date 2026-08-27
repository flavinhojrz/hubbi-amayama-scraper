"""T162 — fallback nunca ocorre entre specs sem equivalência comprovada (FR-023)."""

from amayama_scraper.assets.fallback import resolve_image
from amayama_scraper.equivalence.cluster import build_equivalence_class

SCOPE = "AMAYAMA:VOLKSWAGEN:AMAROK:AMA-BR"


def test_spec_not_a_member_of_the_cluster_gets_no_fallback():
    cluster = build_equivalence_class(
        scope=SCOPE,
        normalizer_version="v1",
        fingerprint_version="v1",
        spec_parts_hash="x" * 64,
        member_spec_refs=("spec-b", "spec-c"),
        representative_spec_ref="spec-b",
    )
    # spec-a is NOT a member of this cluster — no equivalence proven with spec-b/spec-c
    result = resolve_image(
        spec_identity_ref="spec-a",
        own_image_refs=(),
        cluster=cluster,
        member_own_image_refs={"spec-b": ("https://x/b.jpg",)},
    )
    assert result is None


def test_other_member_without_own_images_yields_no_fallback():
    cluster = build_equivalence_class(
        scope=SCOPE,
        normalizer_version="v1",
        fingerprint_version="v1",
        spec_parts_hash="x" * 64,
        member_spec_refs=("spec-a", "spec-b"),
        representative_spec_ref="spec-a",
    )
    result = resolve_image(
        spec_identity_ref="spec-a",
        own_image_refs=(),
        cluster=cluster,
        member_own_image_refs={"spec-b": ()},
    )
    assert result is None
