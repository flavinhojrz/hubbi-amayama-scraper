"""Part — peça associada a um spec entry via schema (data-model.md §3)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Part:
    schema_id: str
    """Redundante por conveniência de fingerprint (ver normalization-fingerprint-contracts.md)."""

    position_pnc: str
    oem_code: str | None = None
    description: str | None = None
    details: str | None = None
    period_application_text: str | None = None
    pr_codes: tuple[str, ...] = field(default_factory=tuple)
    quantity: str | None = None
    image_url: str | None = None

    def __post_init__(self) -> None:
        if not self.schema_id or not self.schema_id.strip():
            raise ValueError("Part.schema_id must not be empty")
        if not self.position_pnc or not self.position_pnc.strip():
            raise ValueError("Part.position_pnc must not be empty")
