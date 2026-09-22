"""Shared enums for capture routing (research.md §16, DEC-001)."""

from __future__ import annotations

from enum import StrEnum


class CaptureKind(StrEnum):
    """Roteia para um dos três parsers (contracts/domain-contracts.md)."""

    MARKET_INDEX = "MARKET_INDEX"
    SPEC_NAVIGATION = "SPEC_NAVIGATION"
    #: Página de UMA categoria declarada na navegação da spec (o mesmo
    #: `.epcVariation__schemaGroups`/`.epcVariation__schemas` de SPEC_NAVIGATION,
    #: mas navegada para a URL própria da categoria — nunca a página base).
    #: Existe porque a página base pode mostrar cards de apenas um subconjunto
    #: das categorias declaradas (causa raiz do bug de manifest truncado) —
    #: cada categoria declarada precisa ser visitada individualmente para que
    #: seu universo real de grupos seja conhecido.
    SPEC_CATEGORY_DETAIL = "SPEC_CATEGORY_DETAIL"
    GROUP_DETAIL = "GROUP_DETAIL"


class AcquisitionMode(StrEnum):
    """MANUAL_BROWSER era o único valor válido em 001 (DEC-001) — o enum já
    existia justamente para que uma automação futura só precisasse
    adicionar um novo valor, não alterar o contrato (FR-034 de 001).
    AUTOMATED_BROWSER_CDP (002, DEC-007) é essa automação: transporte real
    via Chrome DevTools Protocol, attach a um Chrome já aberto pelo
    operador (research.md §6 de 002). Nenhuma lógica de accept_capture()/
    process_capture() ramifica sobre o valor específico — ambos são
    tratados de forma opaca e idêntica pelo núcleo."""

    MANUAL_BROWSER = "MANUAL_BROWSER"
    AUTOMATED_BROWSER_CDP = "AUTOMATED_BROWSER_CDP"
