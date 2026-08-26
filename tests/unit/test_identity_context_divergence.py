"""T093 — expected_identity_context divergence detection (data-model.md §4b)."""

from amayama_scraper.domain.identity import ExpectedIdentityContext, SpecIdentity
from amayama_scraper.parsing.identity_context import detect_identity_context_divergence


def make_identity(**overrides: object) -> SpecIdentity:
    defaults: dict[str, object] = dict(
        source="AMAYAMA",
        manufacturer="VOLKSWAGEN",
        vehicle_model="AMAROK",
        market="AMA-BR",
        model_code="S7BC8A",
        amayama_catalog_id="62184",
        production_period_raw="2018-2023",
        source_url="https://x/s7bc8a-62184",
    )
    defaults.update(overrides)
    return SpecIdentity(**defaults)  # type: ignore[arg-type]


def test_compatible_context_no_divergence():
    expected = ExpectedIdentityContext(
        market="AMA-BR", model_code="S7BC8A", amayama_catalog_id="62184"
    )
    divergence = detect_identity_context_divergence(expected, make_identity())
    assert divergence == {}


def test_model_code_divergent():
    expected = ExpectedIdentityContext(model_code="WRONGCODE")
    divergence = detect_identity_context_divergence(expected, make_identity())
    assert divergence["model_code"] == ("WRONGCODE", "S7BC8A")


def test_amayama_catalog_id_divergent():
    expected = ExpectedIdentityContext(amayama_catalog_id="99999")
    divergence = detect_identity_context_divergence(expected, make_identity())
    assert divergence["amayama_catalog_id"] == ("99999", "62184")


def test_market_divergent():
    expected = ExpectedIdentityContext(market="AMA-US")
    divergence = detect_identity_context_divergence(expected, make_identity())
    assert divergence["market"] == ("AMA-US", "AMA-BR")


def test_absent_expected_context_no_error_no_divergence():
    divergence = detect_identity_context_divergence(None, make_identity())
    assert divergence == {}


def test_partial_context_only_checks_provided_fields():
    expected = ExpectedIdentityContext(model_code="S7BC8A")  # market/catalog_id not provided
    divergence = detect_identity_context_divergence(expected, make_identity())
    assert divergence == {}
