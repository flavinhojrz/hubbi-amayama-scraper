"""T066 — classify_capture() single-signal cases (contracts/input-contracts.md §2)."""

from pathlib import Path

from amayama_scraper.ingestion.capture_kind import CaptureKind
from amayama_scraper.validation.classify import classify_capture
from amayama_scraper.validation.types import ValidationOutcome

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

_VALID_GROUP_DETAIL = b"""
<html><body>
  <div class="epcVariation__details"></div>
  <div class="epcSchema__schemas">
    <div class="epcSchema__schema" data-id="SCH-1">
      <table class="entriesTable"></table>
    </div>
  </div>
</body></html>
"""


def test_challenge_only():
    html = (FIXTURES / "challenge_cloudflare.html").read_bytes()
    result = classify_capture(html, CaptureKind.GROUP_DETAIL)
    assert result.primary_outcome is ValidationOutcome.CHALLENGE


def test_translation_only():
    html = (FIXTURES / "translation_contaminated.html").read_bytes()
    result = classify_capture(html, CaptureKind.GROUP_DETAIL)
    assert result.primary_outcome is ValidationOutcome.TRANSLATION_CONTAMINATED


def test_invalid_only():
    html = (FIXTURES / "invalid_structure.html").read_bytes()
    result = classify_capture(html, CaptureKind.GROUP_DETAIL)
    assert result.primary_outcome is ValidationOutcome.INVALID


def test_incomplete_only():
    html = (FIXTURES / "incomplete_capture.html").read_bytes()
    result = classify_capture(html, CaptureKind.GROUP_DETAIL)
    assert result.primary_outcome is ValidationOutcome.INCOMPLETE


def test_accepted_when_no_signal():
    result = classify_capture(_VALID_GROUP_DETAIL, CaptureKind.GROUP_DETAIL)
    assert result.primary_outcome is ValidationOutcome.ACCEPTED


def test_evidence_always_present_for_computable_signals():
    result = classify_capture(_VALID_GROUP_DETAIL, CaptureKind.GROUP_DETAIL)
    assert set(result.evidence) >= {
        "challenge_detected",
        "translation_contaminated_detected",
        "incomplete_detected",
        "invalid_structure_detected",
    }
