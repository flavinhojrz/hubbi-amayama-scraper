"""T245 — 2HBC3X-56060 <-> S1BC3X-56087 (SC-005).

SAMPLE-LEVEL EXACT only (DEC-004, spec.md §Decisions, 2026-08-27
clarification): real `engine/100`, `front-axle-steering/407` and
`body/800` group-detail pages captured for both specs, run through the
real parser -> real normalization -> real `category_fingerprint()`
(which itself calls `group_fingerprint()`/`part_fingerprint()`
internally). Equal fingerprints prove the sampled groups' parts are
identical content — nothing more.

This intentionally never claims WHOLE-SPEC EXACT: that would require
`finalize_spec_entry()` -> `SpecSnapshot` -> `evaluate_equivalence()`
with `collection_complete=True` on both sides (i.e. all 108 real groups
per spec collected, not a 3-group sample) — genuinely out of scope for
DEC-004's sample. It would also currently have to pass through
`process_capture()`/`classify_capture()`, which has a separate, known,
out-of-scope false positive on full untrimmed real Amayama pages (a
site-wide, always-present `g-recaptcha` sign-up widget trips the
CHALLENGE detector even on pages with zero actual challenge) — see
tests/regression/README.md "Known follow-up". Neither of those two
unrelated facts is worked around here.
"""

from __future__ import annotations

from tests.regression._support import group_detail_to_category, load_group_detail, load_manifest

from amayama_scraper.fingerprints.category import category_fingerprint

SAMPLE_GROUPS = [
    ("engine", "100"),
    ("front-axle-steering", "407"),
    ("body", "800"),
]


def test_manifests_are_real_complete_and_coherent_with_sample():
    for spec_slug, spec_key in (("2hbc3x", "2hbc3x-56060"), ("s1bc3x", "s1bc3x-56087")):
        result = load_manifest(spec_slug, spec_key)

        assert result.critical_error is None
        assert result.manifest.manifest_complete is True
        assert sum(len(c.groups) for c in result.manifest.categories) == 108

        expected = result.manifest.expected_group_keys()
        for category_slug, group_id in SAMPLE_GROUPS:
            assert (category_slug, group_id) in expected


def test_sample_level_exact_parts_across_engine_front_axle_body():
    for category_slug, group_id in SAMPLE_GROUPS:
        a = load_group_detail("2hbc3x", category_slug, group_id)
        b = load_group_detail("s1bc3x", category_slug, group_id)

        assert a.critical_error is None, f"{category_slug}/{group_id} (2hbc3x): {a.critical_error}"
        assert b.critical_error is None, f"{category_slug}/{group_id} (s1bc3x): {b.critical_error}"
        assert len(a.schemas) > 0 and len(b.schemas) > 0

        cat_a = group_detail_to_category(category_slug, group_id, a)
        cat_b = group_detail_to_category(category_slug, group_id, b)

        # SAMPLE-LEVEL EXACT — real content, real normalization+fingerprints,
        # never a claim about the rest of the EPC.
        assert category_fingerprint(cat_a) == category_fingerprint(cat_b)
