"""classify_capture() — outcome único, evidência completa, precedência DEC-003.

contracts/input-contracts.md §2. Precedência normativa (DEC-003, aprovada
pelo PO em 2026-08-26): CHALLENGE > TRANSLATION_CONTAMINATED > INVALID >
INCOMPLETE > ACCEPTED. Todos os sinais computáveis permanecem em
`evidence`, mesmo quando não determinam `primary_outcome`.

Os três capture_kind têm contrato de estrutura comprovado (ver
validation/detectors/structure.py). `StructureContractNotAvailableError`
permanece como sinal explícito para qualquer capture_kind futuro sem
marcadores comprovados — nunca um fallback permissivo para ACCEPTED.
"""

from __future__ import annotations

from datetime import UTC, datetime

from amayama_scraper.ingestion.capture_kind import CaptureKind
from amayama_scraper.validation.detectors.challenge import detect_challenge
from amayama_scraper.validation.detectors.incomplete import detect_incomplete
from amayama_scraper.validation.detectors.structure import (
    StructureContractNotAvailableError,
    detect_invalid_structure,
)
from amayama_scraper.validation.detectors.translation import detect_translation_contamination
from amayama_scraper.validation.types import CaptureValidationResult, ValidationOutcome

__all__ = ["StructureContractNotAvailableError", "classify_capture"]


def classify_capture(raw_content: bytes, capture_kind: CaptureKind) -> CaptureValidationResult:
    html = raw_content.decode("utf-8", errors="replace")
    evidence: dict[str, object] = {}

    challenge = detect_challenge(html)
    evidence["challenge_detected"] = challenge.detected
    if challenge.evidence:
        evidence["challenge_evidence"] = challenge.evidence

    translation = detect_translation_contamination(html)
    evidence["translation_contaminated_detected"] = translation.detected
    if translation.evidence:
        evidence["translation_evidence"] = translation.evidence

    incomplete = detect_incomplete(html)
    evidence["incomplete_detected"] = incomplete.detected
    if incomplete.evidence:
        evidence["incomplete_evidence"] = incomplete.evidence

    structure_detected: bool | None
    try:
        structure = detect_invalid_structure(html, capture_kind)
        structure_detected = structure.detected
        evidence["invalid_structure_detected"] = structure.detected
        if structure.evidence:
            evidence["structure_evidence"] = structure.evidence
    except StructureContractNotAvailableError as exc:
        structure_detected = None
        evidence["invalid_structure_detected"] = None
        evidence["invalid_structure_check_unavailable"] = str(exc)

    primary = _resolve_primary_outcome(
        challenge_detected=challenge.detected,
        translation_detected=translation.detected,
        structure_detected=structure_detected,
        incomplete_detected=incomplete.detected,
        capture_kind=capture_kind,
    )

    return CaptureValidationResult(
        primary_outcome=primary,
        evidence=evidence,
        detected_at=datetime.now(UTC),
    )


def _resolve_primary_outcome(
    *,
    challenge_detected: bool,
    translation_detected: bool,
    structure_detected: bool | None,
    incomplete_detected: bool,
    capture_kind: CaptureKind,
) -> ValidationOutcome:
    """DEC-003: CHALLENGE > TRANSLATION_CONTAMINATED > INVALID > INCOMPLETE > ACCEPTED."""
    if challenge_detected:
        return ValidationOutcome.CHALLENGE
    if translation_detected:
        return ValidationOutcome.TRANSLATION_CONTAMINATED
    if structure_detected is True:
        return ValidationOutcome.INVALID
    if structure_detected is None:
        raise StructureContractNotAvailableError(
            f"cannot determine primary_outcome for capture_kind={capture_kind!r}: "
            "no challenge/translation signal, and structural validity is undecidable "
            "without a comprovada contract for this level"
        )
    if incomplete_detected:
        return ValidationOutcome.INCOMPLETE
    return ValidationOutcome.ACCEPTED
