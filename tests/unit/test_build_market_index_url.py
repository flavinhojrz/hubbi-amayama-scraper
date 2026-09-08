"""build_market_index_url() — evolução multi-modelo (002) + URL segura (004).

A URL do índice de mercado (Nível A) deixou de ser um literal fixo da
Amarok/AMA-BR (era `cli/main.py::MARKET_INDEX_URL`); agora é construída
deterministicamente a partir de um `CollectionContext` (004) já validado —
nunca de strings soltas — mantendo o mesmo formato verificado contra
evidência real (specs/001-amarok-ama-br-ingestion/research.md §21)."""

from amayama_scraper.domain.collection_context import CollectionContext
from amayama_scraper.domain.discovery import build_market_index_url


def test_default_amarok_params_reproduce_the_historical_url():
    context = CollectionContext(manufacturer="VOLKSWAGEN", vehicle_model="AMAROK", market="AMA-BR")
    url = build_market_index_url(context)
    assert url == "https://www.amayama.com/en/genuine-catalogs/epc/volkswagen-overall/amarok/ama-br"


def test_another_vehicle_model_produces_a_different_correct_url():
    context = CollectionContext(manufacturer="VOLKSWAGEN", vehicle_model="GOL", market="AMA-BR")
    url = build_market_index_url(context)
    assert url == "https://www.amayama.com/en/genuine-catalogs/epc/volkswagen-overall/gol/ama-br"

    amarok_context = CollectionContext(
        manufacturer="VOLKSWAGEN", vehicle_model="AMAROK", market="AMA-BR"
    )
    assert url != build_market_index_url(amarok_context)


def test_normalizes_case_and_whitespace():
    context = CollectionContext(
        manufacturer=" Volkswagen ", vehicle_model=" Gol ", market=" AMA-BR "
    )
    url = build_market_index_url(context)
    assert url == "https://www.amayama.com/en/genuine-catalogs/epc/volkswagen-overall/gol/ama-br"
