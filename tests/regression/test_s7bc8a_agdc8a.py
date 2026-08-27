"""T247 — S7BC8A-62184 <-> AGDC8A-62169 (SC-005).

SAMPLE-LEVEL EXACT only (DEC-004, spec.md §Decisions, 2026-08-27
clarification) — see test_2hbc3x_s1bc3x.py module docstring for the full
rationale on why this never claims WHOLE-SPEC EXACT and never routes
around `process_capture()`/`classify_capture()`.

`body/800` sustains real, complete image complementarity: `s7bc8a-62184`
has no own image on any of its 6 real schemas, `agdc8a-62169` has an own
image on all 6 — while the parts content is otherwise SAMPLE-LEVEL EXACT.
"""

from __future__ import annotations

from tests.regression._support import group_detail_to_category, load_group_detail, load_manifest

from amayama_scraper.fingerprints.category import category_fingerprint
from amayama_scraper.fingerprints.image import EMPTY_IMAGE_HASH, image_hash

SAMPLE_GROUPS = [
    ("engine", "100"),
    ("front-axle-steering", "407"),
    ("body", "800"),
]


def test_manifests_are_real_complete_and_coherent_with_sample():
    for spec_slug, spec_key in (("s7bc8a-62184", "s7bc8a-62184"), ("agdc8a-62169", "agdc8a-62169")):
        result = load_manifest(spec_slug, spec_key)

        assert result.critical_error is None
        assert result.manifest.manifest_complete is True
        assert sum(len(c.groups) for c in result.manifest.categories) == 99

        expected = result.manifest.expected_group_keys()
        for category_slug, group_id in SAMPLE_GROUPS:
            assert (category_slug, group_id) in expected


def test_sample_level_exact_parts_across_engine_front_axle_body():
    for category_slug, group_id in SAMPLE_GROUPS:
        a = load_group_detail("s7bc8a-62184", category_slug, group_id)
        b = load_group_detail("agdc8a-62169", category_slug, group_id)

        assert a.critical_error is None, (
            f"{category_slug}/{group_id} (s7bc8a-62184): {a.critical_error}"
        )
        assert b.critical_error is None, (
            f"{category_slug}/{group_id} (agdc8a-62169): {b.critical_error}"
        )
        assert len(a.schemas) > 0 and len(b.schemas) > 0

        cat_a = group_detail_to_category(category_slug, group_id, a)
        cat_b = group_detail_to_category(category_slug, group_id, b)

        # SAMPLE-LEVEL EXACT — real content, real normalization+fingerprints,
        # never a claim about the rest of the EPC.
        assert category_fingerprint(cat_a) == category_fingerprint(cat_b)


def test_body_800_shows_real_complementary_image_coverage_without_affecting_parts_equality():
    a = load_group_detail("s7bc8a-62184", "body", "800")
    b = load_group_detail("agdc8a-62169", "body", "800")

    assert a.critical_error is None
    assert b.critical_error is None

    a_ids = {s.schema_id for s in a.schemas}
    b_ids = {s.schema_id for s in b.schemas}
    assert a_ids == b_ids  # same 6 real schemas on both sides

    cat_a = group_detail_to_category("body", "800", a)
    cat_b = group_detail_to_category("body", "800", b)

    # Parts stay SAMPLE-LEVEL EXACT despite the image difference (Constitution
    # §8/§10: images never participate in parts equivalence).
    assert category_fingerprint(cat_a) == category_fingerprint(cat_b)

    # Real evidence: s7bc8a-62184 has zero own images on this group;
    # agdc8a-62169 has an own image on every one of its 6 schemas — a clean
    # complementary-coverage case (one side fully covered, the other not
    # covered at all), using the real, independent image fingerprint channel
    # (fingerprints/image.py) that finalize_spec_entry() itself uses for
    # SpecSnapshot.image_hash — evaluated here at sample scope, without
    # fabricating a SpecSnapshot.
    a_has_own_images = image_hash((cat_a,)) != EMPTY_IMAGE_HASH
    b_has_own_images = image_hash((cat_b,)) != EMPTY_IMAGE_HASH
    assert a_has_own_images is False
    assert b_has_own_images is True
    for schema in a.schemas:
        assert all(p.image_url is None for p in schema.parts)
    for schema in b.schemas:
        assert all(p.image_url for p in schema.parts)
