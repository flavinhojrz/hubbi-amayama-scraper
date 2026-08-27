"""Detector de INVALID — estrutura mínima esperada, parametrizada por capture_kind.

FR-010; contracts/domain-contracts.md. Para os três níveis, os seletores
já estão evidenciados e comprovados (Nível C: research.md §16 original;
Níveis A/B: research.md §21, evidência real de 2026-08-26) — o detector
verifica a presença de pelo menos um marcador estrutural esperado do nível
correspondente, e HTML irreparavelmente malformado.

`StructureContractNotAvailableError` permanece definido e é levantado se
algum `capture_kind` futuro não tiver marcadores comprovados registrados
aqui — nunca aceita tudo permissivamente por omissão.
"""

from __future__ import annotations

from bs4 import BeautifulSoup

from amayama_scraper.ingestion.capture_kind import CaptureKind
from amayama_scraper.validation.detectors.base import DetectionResult

#: Seletores v1 já comprovados (contracts/domain-contracts.md "Nível C").
GROUP_DETAIL_STRUCTURAL_MARKERS = (
    ".epcVariation__details",
    ".epcSchema__schemas",
    ".entriesTable",
)

#: Seletores comprovados contra evidência real (contracts/domain-contracts.md "Nível A").
MARKET_INDEX_STRUCTURAL_MARKERS = (".epcVariations",)

#: Seletores comprovados contra evidência real (contracts/domain-contracts.md "Nível B").
SPEC_NAVIGATION_STRUCTURAL_MARKERS = (
    ".epcVariation__details",
    ".epcVariation__schemaGroups",
    ".epcVariation__schemas",
)

_MARKERS_BY_CAPTURE_KIND: dict[CaptureKind, tuple[str, ...]] = {
    CaptureKind.MARKET_INDEX: MARKET_INDEX_STRUCTURAL_MARKERS,
    CaptureKind.SPEC_NAVIGATION: SPEC_NAVIGATION_STRUCTURAL_MARKERS,
    CaptureKind.GROUP_DETAIL: GROUP_DETAIL_STRUCTURAL_MARKERS,
}


class StructureContractNotAvailableError(NotImplementedError):
    """Levantado quando não há contrato de estrutura comprovado para o capture_kind.

    NÃO deve ser silenciado nem substituído por um fallback permissivo —
    é o sinal explícito de que uma investigação de evidência real ainda é
    necessária antes de prosseguir para esse capture_kind.
    """


def detect_invalid_structure(html: str, capture_kind: CaptureKind) -> DetectionResult:
    markers = _MARKERS_BY_CAPTURE_KIND.get(capture_kind)
    if markers is None:
        raise StructureContractNotAvailableError(
            f"no comprovada structural contract for capture_kind={capture_kind!r} — "
            "depende de evidência/fixture real (ver research.md, "
            "contracts/domain-contracts.md)"
        )

    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception as exc:  # pragma: no cover - lxml is very tolerant, defensive only
        return DetectionResult(detected=True, evidence={"parse_error": str(exc)})

    found_markers = [marker for marker in markers if soup.select(marker)]
    if found_markers:
        return DetectionResult(detected=False, evidence={"found_markers": found_markers})

    return DetectionResult(
        detected=True,
        evidence={"expected_markers": list(markers), "found_markers": []},
    )
