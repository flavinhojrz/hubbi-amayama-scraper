"""T246 — S6BC74-61127 <-> S7BC74-61187 (SC-005).

SAMPLE-LEVEL EXACT only (DEC-004, spec.md §Decisions, 2026-08-27
clarification) — see test_2hbc3x_s1bc3x.py module docstring for the full
rationale on why this never claims WHOLE-SPEC EXACT and never routes
around `process_capture()`/`classify_capture()`.

Bug fix (2026-09-10): `parsing/selectors.py::IMAGE` (`.imgMap img[src]`)
never matched real fetch()-captured group pages — the real `<img>` itself
carries class `imgMap` there, with no wrapping element of the same class
(that wrapper only appears in a full-navigate()+JS capture). Every group
below was previously (mis)reported as image-empty on both sides purely
because of that selector bug — corrected here against the real fixtures:
`engine/100`, `front-axle-steering/407`, `body/800` and
`access-infotainment-miscell/019` all genuinely carry the same,
identical image on both `s6bc74`/`s7bc74` sides (never asymmetric — the
originally documented "asymmetry" on `019` was itself an artifact of the
same bug, not real site content). What the second half of this file still
verifies is real and unaffected by the fix: images (now correctly
extracted) never participate in parts equivalence (Constitution §8, §10).
"""

from __future__ import annotations

from tests.regression._support import group_detail_to_category, load_group_detail, load_manifest

from amayama_scraper.fingerprints.category import category_fingerprint
from amayama_scraper.fingerprints.image import EMPTY_IMAGE_HASH, image_hash
from amayama_scraper.fingerprints.part import part_fingerprint

SAMPLE_GROUPS = [
    ("engine", "100"),
    ("front-axle-steering", "407"),
    ("body", "800"),
    ("access-infotainment-miscell", "019"),
]

IMAGE_ASYMMETRIC_SCHEMAS = ("19010", "19011")


def test_manifests_are_real_complete_and_coherent_with_sample():
    for spec_slug, spec_key in (("s6bc74", "s6bc74-61127"), ("s7bc74", "s7bc74-61187")):
        result = load_manifest(spec_slug, spec_key)

        assert result.critical_error is None
        # Bug fix (manifest truncado): a single-page parse is never
        # authoritatively complete by itself anymore (parsing/
        # spec_group_manifest.py) — completeness now requires visiting every
        # declared category on its own URL (orchestration/collection_driver.py
        # ::discover_spec_manifest()), out of scope for this sample-level
        # regression (see module docstring). What real evidence DOES support
        # here: every category declared in this real page's own nav is
        # backed by at least one card ON THIS SAME PAGE — this specific real
        # capture was not itself truncated.
        assert result.manifest.manifest_complete is False
        declared = result.manifest.validation_evidence["declared_category_urls"]
        assert {c.category_slug for c in result.manifest.categories} == set(declared)
        assert sum(len(c.groups) for c in result.manifest.categories) == 108

        expected = result.manifest.expected_group_keys()
        for category_slug, group_id in SAMPLE_GROUPS:
            assert (category_slug, group_id) in expected


def test_sample_level_exact_parts_across_sample():
    for category_slug, group_id in SAMPLE_GROUPS:
        a = load_group_detail("s6bc74", category_slug, group_id)
        b = load_group_detail("s7bc74", category_slug, group_id)

        assert a.critical_error is None, f"{category_slug}/{group_id} (s6bc74): {a.critical_error}"
        assert b.critical_error is None, f"{category_slug}/{group_id} (s7bc74): {b.critical_error}"
        assert len(a.schemas) > 0 and len(b.schemas) > 0

        cat_a = group_detail_to_category(category_slug, group_id, a)
        cat_b = group_detail_to_category(category_slug, group_id, b)

        # SAMPLE-LEVEL EXACT for every sampled group, regardless of the
        # (now correctly extracted, always symmetric) image evidence
        # checked separately below.
        assert category_fingerprint(cat_a) == category_fingerprint(cat_b)


def test_engine_and_front_axle_and_body_have_symmetric_image_evidence_on_both_sides():
    """Corrected real evidence (2026-09-10, see module docstring): all three
    groups carry the same, non-empty image on both sides — never empty."""
    for category_slug, group_id in (
        ("engine", "100"),
        ("front-axle-steering", "407"),
        ("body", "800"),
    ):
        a = load_group_detail("s6bc74", category_slug, group_id)
        b = load_group_detail("s7bc74", category_slug, group_id)
        a_images = {p.image_url for s in a.schemas for p in s.parts}
        b_images = {p.image_url for s in b.schemas for p in s.parts}
        assert a_images and all(a_images)
        assert a_images == b_images


def test_access_infotainment_miscell_019_image_presence_does_not_affect_parts_equality():
    a = load_group_detail("s6bc74", "access-infotainment-miscell", "019")
    b = load_group_detail("s7bc74", "access-infotainment-miscell", "019")

    assert a.critical_error is None
    assert b.critical_error is None

    a_by_schema = {s.schema_id: s for s in a.schemas}
    b_by_schema = {s.schema_id: s for s in b.schemas}
    for schema_id in IMAGE_ASYMMETRIC_SCHEMAS:
        assert schema_id in a_by_schema
        assert schema_id in b_by_schema

    for schema_id in IMAGE_ASYMMETRIC_SCHEMAS:
        schema_a, schema_b = a_by_schema[schema_id], b_by_schema[schema_id]

        # Corrected real evidence: both sides carry the same image on this
        # schema (see module docstring) — the originally documented
        # asymmetry was a selector bug, not real site content.
        assert all(p.image_url for p in schema_a.parts)
        assert {p.image_url for p in schema_a.parts} == {p.image_url for p in schema_b.parts}

        # part_fingerprint() never includes image_url (Constitution §10) —
        # matching parts (by pnc) fingerprint identically regardless.
        parts_a = {p.position_pnc: p.to_part() for p in schema_a.parts}
        parts_b = {p.position_pnc: p.to_part() for p in schema_b.parts}
        assert set(parts_a) == set(parts_b)
        for pnc, part_a in parts_a.items():
            assert part_fingerprint(part_a) == part_fingerprint(parts_b[pnc])

    # Rolled up to category level (the real function finalize_spec_entry()
    # itself calls): parts are still SAMPLE-LEVEL EXACT for this group...
    cat_a = group_detail_to_category("access-infotainment-miscell", "019", a)
    cat_b = group_detail_to_category("access-infotainment-miscell", "019", b)
    assert category_fingerprint(cat_a) == category_fingerprint(cat_b)

    # ...and the independent image channel (Constitution §8: "Imagens não
    # participam da decisão de equivalência de peças") is real, non-empty,
    # and identical on both sides — never leaking into parts equivalence.
    tree_a, tree_b = (cat_a,), (cat_b,)
    assert image_hash(tree_a) != EMPTY_IMAGE_HASH
    assert image_hash(tree_b) != EMPTY_IMAGE_HASH
    assert image_hash(tree_a) == image_hash(tree_b)
