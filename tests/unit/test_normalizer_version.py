"""T111 — normalizer_version determinístico e anexado ao resultado normalizado."""

from amayama_scraper.domain.part import Part
from amayama_scraper.normalization.version import NORMALIZER_VERSION, apply_normalization


def test_normalizer_version_is_the_documented_string():
    assert NORMALIZER_VERSION == "amayama-normalizer-v1"


def test_apply_normalization_attaches_version_and_normalizes_fields():
    part = Part(
        schema_id="  407  ",
        position_pnc="  a01  ",
        oem_code="1K0 407 151",
        description="  Control  arm  ",
        details=None,
        period_application_text="08.2010-12.2015",
        pr_codes=("px1", "pj1"),
        quantity="1",
        image_url="https://x/img.jpg",
    )
    result = apply_normalization(part)

    assert result.normalizer_version == NORMALIZER_VERSION
    assert result.part.schema_id == "407"
    assert result.part.position_pnc == "A01"
    assert result.part.oem_code == "1K0407151"
    assert result.part.description == "Control arm"
    assert result.part.details is None
    assert result.part.pr_codes == ("PJ1", "PX1")
    assert result.part.image_url == "https://x/img.jpg"


def test_apply_normalization_is_deterministic():
    part = Part(schema_id="1", position_pnc="a1", oem_code="abc")
    assert apply_normalization(part) == apply_normalization(part)
