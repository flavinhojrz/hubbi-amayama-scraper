"""T019 — SpecGroupManifest authority conditions (data-model.md §15, research.md §17)."""

from datetime import UTC, datetime

import pytest

from amayama_scraper.domain.hierarchy import DuplicateGroupIdError
from amayama_scraper.domain.manifest import (
    ManifestCategory,
    ManifestGroupRef,
    SpecGroupManifest,
    is_manifest_authoritative,
)


def make_manifest(**overrides: object) -> SpecGroupManifest:
    defaults: dict[str, object] = dict(
        spec_key="spec-key-1",
        source_capture_id="capture-nav-1",
        discovered_at=datetime(2026, 8, 26, tzinfo=UTC),
        categories=(
            ManifestCategory(
                category_slug="front-axle-steering",
                groups=(ManifestGroupRef(group_id="407", source_url="https://x/407"),),
            ),
        ),
        manifest_complete=True,
    )
    defaults.update(overrides)
    return SpecGroupManifest(**defaults)  # type: ignore[arg-type]


def test_authoritative_when_complete():
    manifest = make_manifest(manifest_complete=True)
    assert is_manifest_authoritative(manifest) is True


def test_not_authoritative_when_incomplete():
    manifest = make_manifest(manifest_complete=False)
    assert is_manifest_authoritative(manifest) is False


def test_not_authoritative_when_none():
    assert is_manifest_authoritative(None) is False


def test_duplicate_group_id_within_same_category_raises():
    with pytest.raises(DuplicateGroupIdError):
        ManifestCategory(
            category_slug="front-axle-steering",
            groups=(
                ManifestGroupRef(group_id="407", source_url="https://x/407"),
                ManifestGroupRef(group_id="407", source_url="https://x/407-dup"),
            ),
        )


def test_expected_group_keys_covers_all_categories():
    manifest = make_manifest(
        categories=(
            ManifestCategory(
                category_slug="front-axle-steering",
                groups=(ManifestGroupRef(group_id="407", source_url="https://x/407"),),
            ),
            ManifestCategory(
                category_slug="rear-axle",
                groups=(ManifestGroupRef(group_id="1", source_url="https://x/1"),),
            ),
        )
    )
    keys = manifest.expected_group_keys()
    assert keys == frozenset({("front-axle-steering", "407"), ("rear-axle", "1")})
