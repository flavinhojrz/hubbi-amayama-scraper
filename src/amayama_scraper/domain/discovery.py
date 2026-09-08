"""DiscoveredSpecEntry — Nível A (market index) discovery record (data-model.md §14).

Closes FR-001: implements the enumeration output that was missing before
the TASKS revision. Converts into a full SpecIdentity by supplying the
constants fixed for this MVP scope (source/manufacturer/vehicle_model).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from amayama_scraper.domain.collection_context import CollectionContext
from amayama_scraper.domain.identity import SpecIdentity

_MARKET_INDEX_URL_TEMPLATE = "https://www.amayama.com/en/genuine-catalogs/epc/{manufacturer}-overall/{vehicle_model}/{market}"


def build_market_index_url(context: CollectionContext) -> str:
    """Constrói a URL do índice de mercado (Nível A) deterministicamente.

    Reproduz o formato verificado contra evidência real para
    Volkswagen/Amarok/AMA-BR (specs/001-amarok-ama-br-ingestion/research.md
    §21): `.../epc/<manufacturer>-overall/<vehicle_model>/<market>`.

    Recebe `CollectionContext` (não strings soltas, 004) — seus componentes
    já são validados/normalizados na construção (apenas letras, dígitos e
    hífen simples: nunca `/`, `\\`, `..`, `?`, `#`, `:` ou vazio), então esta
    função só precisa de `lower()` (transformação sem perda e sem colisão —
    dois componentes canônicos distintos nunca colapsam na mesma URL). Nunca
    parte de uma URL/spec/catalog_id hardcoded — apenas do contexto de
    escopo escolhido pelo operador.
    """
    return _MARKET_INDEX_URL_TEMPLATE.format(
        manufacturer=context.manufacturer.lower(),
        vehicle_model=context.vehicle_model.lower(),
        market=context.market.lower(),
    )


@dataclass(frozen=True, slots=True)
class DiscoveredSpecEntry:
    market: str
    model_code: str
    amayama_catalog_id: str
    source_url: str
    source_capture_id: str
    production_period_raw: str | None = None
    production_start: date | None = None
    production_end: date | None = None
    grade: str | None = None
    configuration: str | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "market",
            "model_code",
            "amayama_catalog_id",
            "source_url",
            "source_capture_id",
        ):
            value = getattr(self, field_name)
            if not value or not value.strip():
                raise ValueError(f"DiscoveredSpecEntry.{field_name} must not be empty")

    def to_spec_identity(
        self, *, source: str, manufacturer: str, vehicle_model: str
    ) -> SpecIdentity:
        """Complete the constant scope fields to produce a full SpecIdentity.

        Never invents a field absent from discovery — only adds the
        constants fixed for this MVP scope (source/manufacturer/vehicle_model).
        """
        return SpecIdentity(
            source=source,
            manufacturer=manufacturer,
            vehicle_model=vehicle_model,
            market=self.market,
            model_code=self.model_code,
            amayama_catalog_id=self.amayama_catalog_id,
            production_period_raw=self.production_period_raw or "",
            source_url=self.source_url,
            production_start=self.production_start,
            production_end=self.production_end,
            grade=self.grade,
            configuration=self.configuration,
        )
