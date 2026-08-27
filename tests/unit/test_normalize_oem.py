"""T102 — normalize_oem(): strip + upper + remoção de whitespace interno técnico."""

from amayama_scraper.normalization.oem import normalize_oem


def test_strips_and_uppercases():
    assert normalize_oem("  1k0407151  ") == "1K0407151"


def test_removes_internal_technical_whitespace():
    assert normalize_oem("1K0 407 151") == "1K0407151"


def test_removes_internal_nbsp():
    assert normalize_oem("1K0\xa0407\xa0151") == "1K0407151"
