"""T015 — DiscoveredSpecEntry (Nível A). FR-001, FR-003..FR-005; data-model.md §14."""

import pytest

from amayama_scraper.domain.discovery import DiscoveredSpecEntry


def make_entry(**overrides: object) -> DiscoveredSpecEntry:
    defaults = dict(
        market="AMA-BR",
        model_code="S7BC8A",
        amayama_catalog_id="62184",
        source_url="https://amayama.example/s7bc8a-62184",
        source_capture_id="capture-1",
        production_period_raw="2018-2023",
    )
    defaults.update(overrides)
    return DiscoveredSpecEntry(**defaults)  # type: ignore[arg-type]


def test_fields_preserved_when_present():
    entry = make_entry(grade="Highline", configuration="4Motion")
    assert entry.market == "AMA-BR"
    assert entry.grade == "Highline"
    assert entry.configuration == "4Motion"


def test_optional_fields_absent_not_error():
    entry = make_entry(production_period_raw=None, grade=None, configuration=None)
    assert entry.production_period_raw is None
    assert entry.grade is None


def test_open_ended_period_allowed():
    entry = make_entry(production_period_raw="2018-present", production_end=None)
    assert entry.production_end is None
    assert entry.production_period_raw == "2018-present"


def test_model_code_alone_not_sufficient_two_entries_distinct_by_catalog_id():
    a = make_entry(amayama_catalog_id="62184")
    b = make_entry(amayama_catalog_id="61189")
    assert a.model_code == b.model_code
    ia = a.to_spec_identity(source="AMAYAMA", manufacturer="VOLKSWAGEN", vehicle_model="AMAROK")
    ib = b.to_spec_identity(source="AMAYAMA", manufacturer="VOLKSWAGEN", vehicle_model="AMAROK")
    assert ia.stable_key() != ib.stable_key()


def test_to_spec_identity_does_not_invent_fields():
    entry = make_entry(grade=None, configuration=None)
    identity = entry.to_spec_identity(
        source="AMAYAMA", manufacturer="VOLKSWAGEN", vehicle_model="AMAROK"
    )
    assert identity.grade is None
    assert identity.configuration is None
    assert identity.market == entry.market
    assert identity.model_code == entry.model_code
    assert identity.amayama_catalog_id == entry.amayama_catalog_id


@pytest.mark.parametrize(
    "field_name", ["market", "model_code", "amayama_catalog_id", "source_url", "source_capture_id"]
)
def test_required_fields_cannot_be_empty(field_name: str) -> None:
    with pytest.raises(ValueError):
        make_entry(**{field_name: ""})
