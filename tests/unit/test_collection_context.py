"""CollectionContext / normalize_scope_component / build_scope / parse_scope
(004 — correção de robustez da generalização multi-modelo).

FR-010 a FR-024: normalização canônica única, rejeição de componentes
vazios/com delimitador/com caracteres inseguros, round-trip
context -> scope -> context, preservação exata do scope histórico da Amarok.
"""

from __future__ import annotations

import pytest

from amayama_scraper.domain.collection_context import (
    SOURCE,
    CollectionContext,
    InvalidScopeComponentError,
    InvalidScopeError,
    build_scope,
    normalize_scope_component,
    parse_scope,
)

# --- normalize_scope_component -----------------------------------------


def test_trims_whitespace_and_uppercases():
    assert normalize_scope_component(" gol ", field_name="x") == "GOL"


def test_leading_trailing_whitespace_never_produces_a_different_context():
    assert normalize_scope_component(" GOL ", field_name="x") == normalize_scope_component(
        "GOL", field_name="x"
    )


@pytest.mark.parametrize("value", ["", "   ", "\t\n"])
def test_rejects_empty_after_normalization(value: str):
    with pytest.raises(InvalidScopeComponentError):
        normalize_scope_component(value, field_name="x")


@pytest.mark.parametrize(
    "value",
    [
        "AMA:BR",  # scope delimiter
        "AMA/BR",
        "AMA\\BR",
        "AMA..BR",
        "AMA?BR",
        "AMA#BR",
        "AMA BR",  # internal whitespace — never silently turned into a hyphen
        "AMA_BR",
        "-AMABR",  # leading hyphen
        "AMABR-",  # trailing hyphen
    ],
)
def test_rejects_unsafe_or_ambiguous_characters(value: str):
    with pytest.raises(InvalidScopeComponentError):
        normalize_scope_component(value, field_name="x")


@pytest.mark.parametrize("value", ["AMA-BR", "AMAROK", "VOLKSWAGEN", "T-CROSS", "A1B2"])
def test_accepts_real_world_shaped_values(value: str):
    assert normalize_scope_component(value, field_name="x") == value


# --- Unicode: rejeição ANTES de qualquer .upper(), nunca transliteração ---
# (004 Blocker 2 — achado do Codex: str.upper() do Python pode EXPANDIR
# caracteres Unicode em múltiplos ASCII — "ß"->"SS", "ﬀ"->"FF" — o que
# colidiria com um input ASCII genuinamente diferente se o alfabeto fosse
# validado só depois do .upper()).


def test_eszett_is_rejected_never_transliterated_to_ss():
    """'ß'.upper() == 'SS' em Python — provar que isso NUNCA acontece aqui."""
    with pytest.raises(InvalidScopeComponentError):
        normalize_scope_component("ß", field_name="x")
    # a prova de ausência de colisão: 'ß' nunca produz NENHUM componente
    # (portanto nunca pode coincidir com o de 'SS', que é aceito à parte).
    assert normalize_scope_component("SS", field_name="x") == "SS"


def test_ligature_ff_is_rejected_never_transliterated():
    """'ﬀ'.upper() == 'FF' em Python — provar que isso NUNCA acontece aqui."""
    with pytest.raises(InvalidScopeComponentError):
        normalize_scope_component("ﬀ", field_name="x")
    assert normalize_scope_component("FF", field_name="x") == "FF"


@pytest.mark.parametrize("value", ["é", "ñ", "ü", "ç", "GÓL", "AMAROḰ"])
def test_accented_characters_are_rejected(value: str):
    with pytest.raises(InvalidScopeComponentError):
        normalize_scope_component(value, field_name="x")


def test_cyrillic_homoglyph_visually_identical_to_ascii_a_is_rejected():
    """U+0410 (CYRILLIC CAPITAL LETTER A, 'А') é visualmente indistinguível
    de 'A' (U+0041) em muitas fontes, mas é um caractere Unicode diferente —
    deve ser rejeitado, nunca aceito como se fosse o 'A' ASCII."""
    homoglyph_a = "А"
    assert homoglyph_a != "A"  # são pontos de código diferentes
    with pytest.raises(InvalidScopeComponentError):
        normalize_scope_component(f"GOL-{homoglyph_a}MAROK", field_name="x")
    # a versão genuinamente ASCII, sem o homóglifo, é aceita normalmente —
    # prova de que não há confusão silenciosa entre as duas.
    assert normalize_scope_component("GOL-AMAROK", field_name="x") == "GOL-AMAROK"


@pytest.mark.parametrize("value", ["GOL", "AMA-BR", "T-CROSS", "A1B2"])
def test_pure_ascii_equivalents_are_still_accepted(value: str):
    """Nenhuma das rejeições de Unicode acima afeta o caminho ASCII válido."""
    assert normalize_scope_component(value, field_name="x") == value


def test_collection_context_rejects_non_ascii_before_touching_case():
    with pytest.raises(InvalidScopeComponentError):
        CollectionContext(manufacturer="VOLKSWAGEN", vehicle_model="ß", market="AMA-BR")


# --- CollectionContext ---------------------------------------------------


def test_context_normalizes_all_fields_on_construction():
    context = CollectionContext(
        manufacturer=" volkswagen ", vehicle_model=" gol ", market=" ama-br "
    )
    assert context.manufacturer == "VOLKSWAGEN"
    assert context.vehicle_model == "GOL"
    assert context.market == "AMA-BR"
    assert context.source == SOURCE == "AMAYAMA"


def test_context_requires_manufacturer_vehicle_model_and_market_explicitly():
    with pytest.raises(TypeError):
        CollectionContext()  # type: ignore[call-arg]


@pytest.mark.parametrize("field_name", ["manufacturer", "vehicle_model", "market"])
def test_context_rejects_empty_component(field_name: str):
    kwargs = dict(manufacturer="VOLKSWAGEN", vehicle_model="AMAROK", market="AMA-BR")
    kwargs[field_name] = ""
    with pytest.raises(InvalidScopeComponentError):
        CollectionContext(**kwargs)


# --- build_scope / parse_scope (round-trip, colisão) ----------------------


def test_build_scope_preserves_the_historical_amarok_scope_exactly():
    context = CollectionContext(manufacturer="VOLKSWAGEN", vehicle_model="AMAROK", market="AMA-BR")
    assert build_scope(context) == "AMAYAMA:VOLKSWAGEN:AMAROK:AMA-BR"
    assert context.scope() == "AMAYAMA:VOLKSWAGEN:AMAROK:AMA-BR"


@pytest.mark.parametrize(
    "manufacturer,vehicle_model,market",
    [
        ("VOLKSWAGEN", "AMAROK", "AMA-BR"),
        ("VOLKSWAGEN", "GOL", "AMA-BR"),
        ("VOLKSWAGEN", "GOL", "AMA-US"),
        ("VOLKSWAGEN", "T-CROSS", "AMA-BR"),
    ],
)
def test_round_trip_context_to_scope_to_context(
    manufacturer: str, vehicle_model: str, market: str
):
    context = CollectionContext(
        manufacturer=manufacturer, vehicle_model=vehicle_model, market=market
    )
    assert parse_scope(build_scope(context)) == context


def test_different_contexts_never_produce_the_same_scope():
    a = CollectionContext(manufacturer="VOLKSWAGEN", vehicle_model="AMAROK", market="AMA-BR")
    b = CollectionContext(manufacturer="VOLKSWAGEN", vehicle_model="GOL", market="AMA-BR")
    c = CollectionContext(manufacturer="VOLKSWAGEN", vehicle_model="AMAROK", market="AMA-US")
    assert len({build_scope(a), build_scope(b), build_scope(c)}) == 3


@pytest.mark.parametrize(
    "scope",
    [
        "",
        "AMAYAMA:VOLKSWAGEN:AMAROK",  # 3 components
        "AMAYAMA:VOLKSWAGEN:AMAROK:AMA-BR:EXTRA",  # 5 components
        "AMAYAMA::AMAROK:AMA-BR",  # empty component
    ],
)
def test_parse_scope_rejects_malformed_strings(scope: str):
    with pytest.raises((InvalidScopeError, InvalidScopeComponentError)):
        parse_scope(scope)


def test_parse_scope_of_the_real_historical_amarok_row_succeeds():
    """Nenhuma migração é necessária: o scope já persistido no banco real da
    Amarok (feature 002) já satisfaz o alfabeto canônico desta feature."""
    context = parse_scope("AMAYAMA:VOLKSWAGEN:AMAROK:AMA-BR")
    assert context == CollectionContext(
        manufacturer="VOLKSWAGEN", vehicle_model="AMAROK", market="AMA-BR"
    )
