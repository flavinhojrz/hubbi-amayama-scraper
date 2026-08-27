"""T056 — CaptureValidationResult outcome enum (contracts/input-contracts.md §2)."""

from amayama_scraper.validation.types import CaptureValidationResult, ValidationOutcome


def test_five_outcomes_exist():
    assert {v.value for v in ValidationOutcome} == {
        "ACCEPTED",
        "CHALLENGE",
        "TRANSLATION_CONTAMINATED",
        "INVALID",
        "INCOMPLETE",
    }


def test_result_holds_evidence_dict():
    result = CaptureValidationResult(
        primary_outcome=ValidationOutcome.CHALLENGE,
        evidence={"challenge_detected": True, "invalid_structure_detected": True},
    )
    assert result.evidence["challenge_detected"] is True
    assert result.evidence["invalid_structure_detected"] is True
