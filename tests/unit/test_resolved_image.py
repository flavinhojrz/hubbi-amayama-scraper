"""T044 — ResolvedImage invariants (data-model.md §10)."""

import pytest

from amayama_scraper.assets.types import ResolvedImage


def test_own_image_no_fallback_fields_required():
    img = ResolvedImage(
        spec_identity_ref="spec-a",
        origin_spec_ref="spec-a",
        image_url_or_ref="https://x/img.jpg",
        is_fallback=False,
    )
    assert img.resolved_within_cluster_key is None


def test_fallback_requires_cluster_key():
    with pytest.raises(ValueError):
        ResolvedImage(
            spec_identity_ref="spec-a",
            origin_spec_ref="spec-b",
            image_url_or_ref="https://x/img.jpg",
            is_fallback=True,
            resolved_within_cluster_key=None,
        )


def test_fallback_with_cluster_key_is_valid():
    img = ResolvedImage(
        spec_identity_ref="spec-a",
        origin_spec_ref="spec-b",
        image_url_or_ref="https://x/img.jpg",
        is_fallback=True,
        resolved_within_cluster_key="cluster-1",
    )
    assert img.origin_spec_ref == "spec-b"
