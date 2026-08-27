"""T080 — extract_category_and_group_from_url() (research.md §19)."""

import pytest

from amayama_scraper.parsing.url_extraction import (
    UrlStructuralDriftError,
    extract_category_and_group_from_url,
)


def test_documented_evidence_example():
    category, group = extract_category_and_group_from_url(
        "https://amayama.example/epc/s1bc3x-56087/front-axle-steering/407"
    )
    assert category == "front-axle-steering"
    assert group == "407"


def test_trailing_slash_ignored():
    category, group = extract_category_and_group_from_url(
        "https://amayama.example/epc/s1bc3x-56087/front-axle-steering/407/"
    )
    assert category == "front-axle-steering"
    assert group == "407"


def test_too_few_segments_raises_drift_error():
    with pytest.raises(UrlStructuralDriftError):
        extract_category_and_group_from_url("https://amayama.example/407")


def test_never_infers_from_translated_text_only_url_path_used():
    # Query string / fragment must not influence the result.
    category, group = extract_category_and_group_from_url(
        "https://amayama.example/epc/s1bc3x-56087/front-axle-steering/407?lang=pt-translated"
    )
    assert category == "front-axle-steering"
    assert group == "407"
