"""T068 — DEC-003: precedência determinística de primary_outcome quando
múltiplos sinais coexistem simultaneamente.

Ordem normativa: CHALLENGE > TRANSLATION_CONTAMINATED > INVALID > INCOMPLETE > ACCEPTED.
evidence sempre preserva todos os sinais computados, mesmo os que não
determinaram primary_outcome.
"""

from pathlib import Path

from amayama_scraper.ingestion.capture_kind import CaptureKind
from amayama_scraper.validation.classify import classify_capture
from amayama_scraper.validation.types import ValidationOutcome

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

# Missing </html>/</body> AND lacks the group-detail structural markers —
# fires both incomplete_detected and invalid_structure_detected.
_INVALID_AND_INCOMPLETE = b"""<html><body>
<div class="totally-unrelated-layout">
"""


def test_challenge_and_invalid_structure_simultaneously_challenge_wins():
    """The challenge fixture also lacks group-detail structural markers —
    both signals fire at once. CHALLENGE must win (DEC-003)."""
    html = (FIXTURES / "challenge_cloudflare.html").read_bytes()
    result = classify_capture(html, CaptureKind.GROUP_DETAIL)

    assert result.primary_outcome is ValidationOutcome.CHALLENGE
    assert result.evidence["challenge_detected"] is True
    assert result.evidence["invalid_structure_detected"] is True  # preserved, not erased


def test_translation_and_invalid_structure_simultaneously_translation_wins():
    """The translation fixture also lacks group-detail structural markers —
    both signals fire at once. TRANSLATION_CONTAMINATED must win (DEC-003)."""
    html = (FIXTURES / "translation_contaminated.html").read_bytes()
    result = classify_capture(html, CaptureKind.GROUP_DETAIL)

    assert result.primary_outcome is ValidationOutcome.TRANSLATION_CONTAMINATED
    assert result.evidence["translation_contaminated_detected"] is True
    assert result.evidence["invalid_structure_detected"] is True  # preserved, not erased


def test_invalid_structure_and_incomplete_simultaneously_invalid_wins():
    result = classify_capture(_INVALID_AND_INCOMPLETE, CaptureKind.GROUP_DETAIL)

    assert result.primary_outcome is ValidationOutcome.INVALID
    assert result.evidence["invalid_structure_detected"] is True
    assert result.evidence["incomplete_detected"] is True  # preserved, not erased
    # neither challenge nor translation fired here
    assert result.evidence["challenge_detected"] is False
    assert result.evidence["translation_contaminated_detected"] is False
