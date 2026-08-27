"""CaptureValidationResult — primary_outcome + evidence (contracts/input-contracts.md §2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class ValidationOutcome(StrEnum):
    ACCEPTED = "ACCEPTED"
    CHALLENGE = "CHALLENGE"
    TRANSLATION_CONTAMINATED = "TRANSLATION_CONTAMINATED"
    INVALID = "INVALID"
    INCOMPLETE = "INCOMPLETE"


@dataclass(frozen=True, slots=True)
class CaptureValidationResult:
    primary_outcome: ValidationOutcome
    evidence: dict[str, object] = field(default_factory=dict)
    detected_at: datetime | None = None
