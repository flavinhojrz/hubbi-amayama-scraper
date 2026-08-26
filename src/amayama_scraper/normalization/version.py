"""apply_normalization() — agregador versionado (contracts/normalization-fingerprint-contracts.md).

Interpretação documentada (composição das regras já definidas, sem
inventar nenhuma nova): a unidade normalizada é um `Part` inteiro — os
sete campos usados por `part_fingerprint` (Phase 6) mais `pr_codes`
(preservado para domínio/export, fora do fingerprint). `normalizer_version`
é anexado ao resultado agregado (`NormalizedPart`), não ao `Part` em si
(que permanece um tipo de domínio puro, sem campo de versão).
"""

from __future__ import annotations

from dataclasses import dataclass

from amayama_scraper.domain.part import Part
from amayama_scraper.normalization.identifiers import normalize_pnc, normalize_schema_id
from amayama_scraper.normalization.oem import normalize_oem
from amayama_scraper.normalization.pr_codes import normalize_pr_codes
from amayama_scraper.normalization.text import normalize_text

NORMALIZER_VERSION = "amayama-normalizer-v1"


@dataclass(frozen=True, slots=True)
class NormalizedPart:
    part: Part
    normalizer_version: str


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = normalize_text(value)
    return normalized or None


def apply_normalization(part: Part) -> NormalizedPart:
    normalized_part = Part(
        schema_id=normalize_schema_id(part.schema_id),
        position_pnc=normalize_pnc(part.position_pnc),
        oem_code=normalize_oem(part.oem_code) if part.oem_code is not None else None,
        description=_normalize_optional_text(part.description),
        details=_normalize_optional_text(part.details),
        period_application_text=_normalize_optional_text(part.period_application_text),
        pr_codes=normalize_pr_codes(part.pr_codes),
        quantity=_normalize_optional_text(part.quantity),
        image_url=part.image_url,
    )
    return NormalizedPart(part=normalized_part, normalizer_version=NORMALIZER_VERSION)
