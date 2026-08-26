"""T164 — ausência de imagem resolvível retorna None, não é erro."""

from amayama_scraper.assets.fallback import resolve_image


def test_no_own_image_no_cluster_returns_none_without_raising():
    result = resolve_image(
        spec_identity_ref="spec-a",
        own_image_refs=(),
        cluster=None,
        member_own_image_refs={},
    )
    assert result is None
