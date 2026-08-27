"""T163 — origin_spec_ref sempre preservado, inclusive em fallback (FR-024, FR-025)."""

from amayama_scraper.assets.fallback import resolve_image
from amayama_scraper.equivalence.cluster import build_equivalence_class

SCOPE = "AMAYAMA:VOLKSWAGEN:AMAROK:AMA-BR"


def test_own_image_origin_is_self():
    result = resolve_image(
        spec_identity_ref="spec-a",
        own_image_refs=("https://x/a.jpg",),
        cluster=None,
        member_own_image_refs={},
    )
    assert result is not None
    assert result.origin_spec_ref == "spec-a"


def test_fallback_origin_is_the_actual_source_never_the_requesting_spec():
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
        member_own_image_refs={"spec-b": ("https://x/b.jpg",)},
    )
    assert result is not None
    assert result.origin_spec_ref == "spec-b"
    assert result.origin_spec_ref != "spec-a"
