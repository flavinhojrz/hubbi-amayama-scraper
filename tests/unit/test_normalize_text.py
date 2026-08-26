"""T100 — normalize_text(): NFKC, NBSP/line-break/whitespace, trim."""

from amayama_scraper.normalization.text import normalize_text


def test_strips_leading_trailing_whitespace():
    assert normalize_text("  hello  ") == "hello"


def test_nbsp_becomes_plain_space():
    assert normalize_text("a\xa0b") == "a b"


def test_crlf_and_cr_become_lf():
    assert normalize_text("a\r\nb\rc") == "a\nb\nc"


def test_collapses_redundant_horizontal_whitespace():
    assert normalize_text("a    b\t\tc") == "a b c"


def test_collapses_blank_lines():
    assert normalize_text("a\n\n\n\nb") == "a\nb"


def test_nfkc_normalizes_compatibility_forms():
    # U+FF21 FULLWIDTH LATIN CAPITAL LETTER A -> "A"
    assert normalize_text("Ａ") == "A"


def test_preserves_punctuation_and_accents():
    assert normalize_text("café, S/N - 1K0.407") == "café, S/N - 1K0.407"
