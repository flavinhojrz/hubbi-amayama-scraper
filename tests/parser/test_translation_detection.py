"""T060 — TRANSLATION_CONTAMINATED detector against fixture (FR-010)."""

from pathlib import Path

from amayama_scraper.validation.detectors.translation import detect_translation_contamination

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_translation_fixture_is_detected():
    html = (FIXTURES / "translation_contaminated.html").read_text()
    result = detect_translation_contamination(html)
    assert result.detected is True
    assert result.evidence


def test_ordinary_page_not_detected_as_translated():
    html = "<html><head><title>Amarok S7BC8A</title></head><body>ok</body></html>"
    result = detect_translation_contamination(html)
    assert result.detected is False
