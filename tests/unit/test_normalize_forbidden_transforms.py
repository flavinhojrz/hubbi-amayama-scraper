"""T109 — regressão negativa: normalização NÃO traduz/stemming/fuzzy/sinonímia/
corrige ortografia/remove acentos arbitrariamente (FR-016)."""

from amayama_scraper.normalization.oem import normalize_oem
from amayama_scraper.normalization.text import normalize_text


def test_no_translation():
    # "Motor" (PT) must not become "Engine" (EN) or vice-versa.
    assert normalize_text("Motor") == "Motor"
    assert normalize_text("Engine") == "Engine"


def test_no_accent_stripping():
    assert normalize_text("côté gauche") == "côté gauche"
    assert normalize_text("ássento") == "ássento"


def test_no_spelling_correction():
    # deliberately misspelled — must pass through unchanged
    assert normalize_text("controll arm") == "controll arm"


def test_oem_case_normalization_is_not_a_synonym_transform():
    # upper()-casing is the only case transform allowed for OEM — no
    # alias/synonym table applied on top of it.
    assert normalize_oem("abc123") == "ABC123"
