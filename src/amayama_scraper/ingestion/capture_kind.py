"""Shared enums for capture routing (research.md §16, DEC-001)."""

from __future__ import annotations

from enum import StrEnum


class CaptureKind(StrEnum):
    """Roteia para um dos três parsers (contracts/domain-contracts.md)."""

    MARKET_INDEX = "MARKET_INDEX"
    SPEC_NAVIGATION = "SPEC_NAVIGATION"
    GROUP_DETAIL = "GROUP_DETAIL"


class AcquisitionMode(StrEnum):
    """Único valor válido nesta feature (DEC-001) — o enum existe para que
    uma automação futura só precise adicionar um novo valor, não alterar
    o contrato (FR-034)."""

    MANUAL_BROWSER = "MANUAL_BROWSER"
