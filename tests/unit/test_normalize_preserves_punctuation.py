"""T108 — regressão negativa: pontuação preservada, nenhuma remoção arbitrária."""

from amayama_scraper.normalization.text import normalize_text


def test_punctuation_is_never_stripped():
    text = "control arm, left side; front (08.2010-12.2015) - S/N"
    assert normalize_text(text) == text


def test_hyphen_and_slash_preserved_in_oem_like_text():
    assert normalize_text("1K0-407/151") == "1K0-407/151"
