"""T097 — assemble_spec_tree() (contracts/domain-contracts.md "Montagem da árvore agregada")."""

from datetime import UTC, datetime

from amayama_scraper.domain.manifest import ManifestCategory, ManifestGroupRef, SpecGroupManifest
from amayama_scraper.parsing.assembly import assemble_spec_tree
from amayama_scraper.parsing.results import ParsedGroupDetail, ParsedPart, ParsedSchema


def make_manifest(**overrides: object) -> SpecGroupManifest:
    defaults: dict[str, object] = dict(
        spec_key="spec-1",
        source_capture_id="nav-1",
        discovered_at=datetime(2026, 8, 26, tzinfo=UTC),
        categories=(
            ManifestCategory(
                category_slug="front-axle-steering",
                groups=(
                    ManifestGroupRef(group_id="407", source_url="https://x/407"),
                    ManifestGroupRef(group_id="408", source_url="https://x/408"),
                ),
            ),
        ),
        manifest_complete=True,
    )
    defaults.update(overrides)
    return SpecGroupManifest(**defaults)  # type: ignore[arg-type]


def test_complete_manifest_all_groups_accepted_produces_full_tree():
    manifest = make_manifest()
    group_details = {
        ("front-axle-steering", "407"): ParsedGroupDetail(
            category_slug="front-axle-steering",
            group_id="407",
            schemas=(
                ParsedSchema(
                    schema_id="SCH-1", parts=(ParsedPart(schema_id="SCH-1", position_pnc="A01"),)
                ),
            ),
        ),
        ("front-axle-steering", "408"): ParsedGroupDetail(
            category_slug="front-axle-steering",
            group_id="408",
            schemas=(),
        ),
    }
    tree = assemble_spec_tree(manifest, group_details)
    assert len(tree) == 1
    category = tree[0]
    assert category.category_slug == "front-axle-steering"
    group_ids = {g.group_id for g in category.groups}
    assert group_ids == {"407", "408"}


def test_missing_group_omitted_produces_partial_tree():
    manifest = make_manifest()
    group_details = {
        ("front-axle-steering", "407"): ParsedGroupDetail(
            category_slug="front-axle-steering", group_id="407", schemas=()
        ),
        # "408" not yet captured
    }
    tree = assemble_spec_tree(manifest, group_details)
    group_ids = {g.group_id for c in tree for g in c.groups}
    assert group_ids == {"407"}  # 408 omitted, not fabricated as empty


def test_truly_empty_group_is_included_not_omitted():
    manifest = make_manifest(
        categories=(
            ManifestCategory(
                category_slug="rear-axle",
                groups=(ManifestGroupRef(group_id="1", source_url="https://x/1"),),
            ),
        )
    )
    group_details = {
        ("rear-axle", "1"): ParsedGroupDetail(category_slug="rear-axle", group_id="1", schemas=())
    }
    tree = assemble_spec_tree(manifest, group_details)
    assert len(tree) == 1
    assert tree[0].groups[0].group_id == "1"
    assert tree[0].groups[0].schemas == ()


def test_no_groups_available_produces_no_category():
    manifest = make_manifest()
    tree = assemble_spec_tree(manifest, {})
    assert tree == ()
