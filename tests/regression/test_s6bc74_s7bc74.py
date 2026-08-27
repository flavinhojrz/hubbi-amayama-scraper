"""T246 — S6BC74-61127 <-> S7BC74-61187 (SC-005).

SAMPLE-LEVEL EXACT only (DEC-004, spec.md §Decisions, 2026-08-27
clarification) — see test_2hbc3x_s1bc3x.py module docstring for the full
rationale on why this never claims WHOLE-SPEC EXACT and never routes
around `process_capture()`/`classify_capture()`.

Real evidence for `engine/100` and `front-axle-steering/407` does NOT
show any image on either side (both empty) — the "difference is only in
image" scenario described by the original task wording is not sustained
by those two groups, and this file does not force it. `body/800` is also
image-empty on both sides. The real group that *does* sustain the image
scenario is `access-infotainment-miscell/019` (schemas `19010`/`19011`):
identical parts, asymmetric image presence — proven below using the same
real, independent fingerprint channels the Constitution (§8, §10)
mandates parts/images never share.
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
        assert result.manifest.manifest_complete is True
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

        # SAMPLE-LEVEL EXACT for every sampled group, including the one that
        # also carries the real image asymmetry (proven separately below).
        assert category_fingerprint(cat_a) == category_fingerprint(cat_b)


def test_engine_and_front_axle_and_body_have_no_image_evidence_on_either_side():
    """Reports the real evidence rather than forcing the "image difference"
    scenario onto groups that do not sustain it (per the 2026-08-27
    clarification)."""
    for category_slug, group_id in (
        ("engine", "100"),
        ("front-axle-steering", "407"),
        ("body", "800"),
    ):
        a = load_group_detail("s6bc74", category_slug, group_id)
        b = load_group_detail("s7bc74", category_slug, group_id)
        a_has_image = any(p.image_url for s in a.schemas for p in s.parts)
        b_has_image = any(p.image_url for s in b.schemas for p in s.parts)
        assert a_has_image is False
        assert b_has_image is False


def test_access_infotainment_miscell_019_image_asymmetry_does_not_affect_parts_equality():
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

        # Real image asymmetry: s6bc74 has none, s7bc74 has one, on both
        # asymmetric schemas.
        assert all(p.image_url is None for p in schema_a.parts)
        assert all(p.image_url for p in schema_b.parts)

        # part_fingerprint() never includes image_url (Constitution §10) —
        # matching parts (by pnc) fingerprint identically despite the
        # image_url difference on the raw Part itself.
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

    # ...while the independent image channel (Constitution §8: "Imagens não
    # participam da decisão de equivalência de peças") genuinely differs,
    # proving the asset difference is real and does not leak into parts
    # equivalence.
    tree_a, tree_b = (cat_a,), (cat_b,)
    assert image_hash(tree_a) == EMPTY_IMAGE_HASH
    assert image_hash(tree_b) != EMPTY_IMAGE_HASH
    assert image_hash(tree_a) != image_hash(tree_b)
