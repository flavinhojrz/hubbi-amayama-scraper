"""T070 — CHALLENGE routes to human-in-the-loop, never treated as empty-valid (FR-011)."""

from amayama_scraper.validation.human_in_the_loop import route_if_challenge
from amayama_scraper.validation.types import CaptureValidationResult, ValidationOutcome


def test_challenge_produces_signal():
    result = CaptureValidationResult(
        primary_outcome=ValidationOutcome.CHALLENGE, evidence={"challenge_detected": True}
    )
    signal = route_if_challenge("https://x/1", result)
    assert signal is not None
    assert signal.source_url == "https://x/1"
    assert signal.evidence["challenge_detected"] is True


def test_accepted_produces_no_signal():
    result = CaptureValidationResult(primary_outcome=ValidationOutcome.ACCEPTED, evidence={})
    assert route_if_challenge("https://x/1", result) is None


def test_challenge_never_treated_as_accepted():
    result = CaptureValidationResult(
        primary_outcome=ValidationOutcome.CHALLENGE, evidence={"challenge_detected": True}
    )
    assert result.primary_outcome is not ValidationOutcome.ACCEPTED
