"""T064 — INCOMPLETE classification against fixture (FR-010)."""

from pathlib import Path

from amayama_scraper.validation.detectors.incomplete import detect_incomplete

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_incomplete_fixture_is_detected():
    html = (FIXTURES / "incomplete_capture.html").read_text()
    result = detect_incomplete(html)
    assert result.detected is True
    assert "</html>" in result.evidence["missing_closing_tags"]


def test_well_formed_page_not_detected_as_incomplete():
    html = "<html><body><p>ok</p></body></html>"
    result = detect_incomplete(html)
    assert result.detected is False
