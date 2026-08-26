"""T158 — imagem própria (is_fallback=False) quando a spec entry tem imagem própria."""

from amayama_scraper.assets.fallback import resolve_image


def test_own_image_used_directly_no_fallback():
    result = resolve_image(
        spec_identity_ref="spec-a",
        own_image_refs=("https://x/a.jpg",),
        cluster=None,
        member_own_image_refs={},
    )
    assert result is not None
    assert result.is_fallback is False
    assert result.origin_spec_ref == "spec-a"
    assert result.image_url_or_ref == "https://x/a.jpg"
    assert result.resolved_within_cluster_key is None


def test_multiple_own_images_pick_lexicographically_smallest_deterministically():
    result = resolve_image(
        spec_identity_ref="spec-a",
        own_image_refs=("https://x/b.jpg", "https://x/a.jpg"),
        cluster=None,
        member_own_image_refs={},
    )
    assert result is not None
    assert result.image_url_or_ref == "https://x/a.jpg"
