"""T058 — CHALLENGE detector against fixture (Constitution §5, FR-010)."""

from pathlib import Path

from amayama_scraper.validation.detectors.challenge import detect_challenge

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_challenge_fixture_is_detected():
    html = (FIXTURES / "challenge_cloudflare.html").read_text()
    result = detect_challenge(html)
    assert result.detected is True
    assert result.evidence  # some signal must be recorded


def test_ordinary_page_not_detected_as_challenge():
    html = "<html><head><title>Amarok S7BC8A</title></head><body>ok</body></html>"
    result = detect_challenge(html)
    assert result.detected is False
