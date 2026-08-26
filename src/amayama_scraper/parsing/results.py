"""Resultados de parsing dos três níveis (contracts/domain-contracts.md)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from amayama_scraper.domain.discovery import DiscoveredSpecEntry
from amayama_scraper.domain.manifest import SpecGroupManifest
from amayama_scraper.domain.part import Part


class FieldStatus(StrEnum):
    PRESENT = "PRESENT"
    ABSENT = "ABSENT"
    PARSE_ERROR = "PARSE_ERROR"


@dataclass(frozen=True, slots=True)
class ParseError:
    message: str
    context: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ParsedPart:
    schema_id: str
    position_pnc: str
    field_status: dict[str, FieldStatus] = field(default_factory=dict)
    oem_code: str | None = None
    description: str | None = None
    details: str | None = None
    period_application_text: str | None = None
    pr_codes: tuple[str, ...] = field(default_factory=tuple)
    quantity: str | None = None
    image_url: str | None = None

    def to_part(self) -> Part:
        """Projeta para o Part de domínio (data-model.md §3) — field_status é
        um detalhe de auditoria de parsing, não do domínio final."""
        return Part(
            schema_id=self.schema_id,
            position_pnc=self.position_pnc,
            oem_code=self.oem_code,
            description=self.description,
            details=self.details,
            period_application_text=self.period_application_text,
            pr_codes=self.pr_codes,
            quantity=self.quantity,
            image_url=self.image_url,
        )


@dataclass(frozen=True, slots=True)
class ParsedSchema:
    schema_id: str
    parts: tuple[ParsedPart, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class ParsedGroupDetail:
    category_slug: str
    group_id: str
    schemas: tuple[ParsedSchema, ...] = field(default_factory=tuple)
    parse_errors: tuple[ParseError, ...] = field(default_factory=tuple)
    critical_error: ParseError | None = None
    parser_version: str | None = None


@dataclass(frozen=True, slots=True)
class ParseMarketIndexResult:
    """Resultado de `parse_market_spec_index()` — Nível A (contracts/domain-contracts.md)."""

    entries: tuple[DiscoveredSpecEntry, ...] = field(default_factory=tuple)
    parse_errors: tuple[ParseError, ...] = field(default_factory=tuple)
    critical_error: ParseError | None = None
    parser_version: str | None = None


@dataclass(frozen=True, slots=True)
class ParseManifestResult:
    """Resultado de `parse_spec_group_manifest()` — Nível B (contracts/domain-contracts.md)."""

    manifest: SpecGroupManifest | None = None
    parse_errors: tuple[ParseError, ...] = field(default_factory=tuple)
    critical_error: ParseError | None = None
    parser_version: str | None = None
