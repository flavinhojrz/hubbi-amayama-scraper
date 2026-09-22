"""Scenario 4 (bug fix — manifest truncado, category-by-category discovery):
a category repeating a group it already reported (e.g. across two visits/
passes of the very same category, or a duplicate entry in its own stored
evidence) is deduplicated correctly — the assembler never raises and never
produces two entries for the same group_id within one category.

`_merge_category_groups()` (orchestration/collection_driver.py) is the exact
function `discover_spec_manifest()` uses to turn a category's stored
`evidence["groups"]` (written by `_route_spec_category_detail()`, see
orchestration/pipeline.py) back into `ManifestGroupRef`s before assembling
the final `ManifestCategory` — dict-keyed by `group_id`, so a repeated
group_id can never survive into `ManifestCategory.__post_init__()`, which
would otherwise raise `DuplicateGroupIdError` (domain/hierarchy.py) for a
genuine duplicate.
"""

from __future__ import annotations

from amayama_scraper.domain.manifest import ManifestGroupRef
from amayama_scraper.orchestration.collection_driver import _merge_category_groups


def test_repeated_group_id_across_two_entries_is_deduplicated():
    evidence_groups = [
        {"group_id": "407", "source_url": "https://x/front-axle-steering/407"},
        {"group_id": "409", "source_url": "https://x/front-axle-steering/409"},
        # "407" reported again (e.g. the category's own page listed it twice,
        # or two visits/passes both reported it) — never a second entry.
        {"group_id": "407", "source_url": "https://x/front-axle-steering/407"},
    ]

    merged = _merge_category_groups(evidence_groups)

    assert merged == {
        "407": ManifestGroupRef(group_id="407", source_url="https://x/front-axle-steering/407"),
        "409": ManifestGroupRef(group_id="409", source_url="https://x/front-axle-steering/409"),
    }
    assert len(merged) == 2  # never 3 — the repeat never produces a duplicate entry


def test_malformed_or_missing_entries_are_skipped_not_raised():
    evidence_groups = [
        {"group_id": "407", "source_url": "https://x/front-axle-steering/407"},
        {"group_id": "", "source_url": "https://x/blank"},  # empty group_id — skipped
        {"group_id": "410"},  # missing source_url — skipped
        "not-a-dict",  # structurally wrong — skipped, never raises
    ]

    merged = _merge_category_groups(evidence_groups)

    assert merged == {
        "407": ManifestGroupRef(group_id="407", source_url="https://x/front-axle-steering/407"),
    }


def test_non_list_input_yields_empty_merge():
    assert _merge_category_groups(None) == {}
    assert _merge_category_groups({}) == {}
