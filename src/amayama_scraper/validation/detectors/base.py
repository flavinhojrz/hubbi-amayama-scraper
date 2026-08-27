"""Shared result type for all validation detectors."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class DetectionResult:
    detected: bool
    evidence: dict[str, object] = field(default_factory=dict)
