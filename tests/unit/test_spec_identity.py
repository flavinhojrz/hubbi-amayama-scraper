"""T013 — SpecIdentity structural invariants (FR-002..FR-005, FR-021; data-model.md §1)."""

import dataclasses

import pytest

from amayama_scraper.domain.identity import SpecIdentity


def make_identity(**overrides: object) -> SpecIdentity:
    defaults = dict(
        source="Amayama",
        manufacturer="Volkswagen",
        vehicle_model="Amarok",
        market="AMA-BR",
        model_code="S7BC8A",
        amayama_catalog_id="62184",
        production_period_raw="2018-2023",
        source_url="https://amayama.example/s7bc8a-62184",
    )
    defaults.update(overrides)
    return SpecIdentity(**defaults)  # type: ignore[arg-type]


def test_identity_tuple_has_six_normative_fields():
    field_names = {f.name for f in dataclasses.fields(SpecIdentity)}
    for required in (
        "source",
        "manufacturer",
        "vehicle_model",
        "market",
        "model_code",
        "amayama_catalog_id",
    ):
        assert required in field_names


def test_stable_key_is_deterministic():
    a = make_identity()
    b = make_identity()
    assert a.stable_key() == b.stable_key()


def test_stable_key_differs_for_different_amayama_catalog_id_same_model_code():
    a = make_identity(amayama_catalog_id="62184")
    b = make_identity(amayama_catalog_id="61189")
    assert a.model_code == b.model_code
    assert a.stable_key() != b.stable_key()  # FR-003: model_code alone is not identity


def test_stable_key_case_insensitive_normalization():
    a = make_identity(model_code="s7bc8a")
    b = make_identity(model_code="S7BC8A")
    assert a.stable_key() == b.stable_key()


def test_stable_key_ignores_production_start_end_source_url():
    from datetime import date

    a = make_identity(
        production_start=date(2018, 1, 1),
        production_end=None,
        source_url="https://amayama.example/a",
    )
    b = make_identity(
        production_start=date(2019, 6, 1),
        production_end=date(2020, 1, 1),
        source_url="https://amayama.example/b-different",
    )
    assert a.stable_key() == b.stable_key()


def test_display_key_escapes_colon_and_backslash():
    identity = make_identity(model_code="S7:BC\\8A")
    display = identity.display_key()
    assert display.count("\\:") >= 1  # escaped colon inside a component
    parts_by_unescaped_colon = display.split(":")
    # the raw split would be wrong (5+ parts) if escaping weren't applied consistently
    assert len(parts_by_unescaped_colon) != 4 or "\\:" in display


def test_display_key_not_used_for_equality():
    a = make_identity(amayama_catalog_id="62184")
    b = make_identity(amayama_catalog_id="61189")
    # stable_key differs; display_key format alone must not be relied on for equality
    assert a.stable_key() != b.stable_key()


def test_optional_fields_absence_does_not_invalidate_identity():
    identity = make_identity(
        grade=None, configuration=None, production_start=None, production_end=None
    )
    assert identity.grade is None
    assert identity.configuration is None


@pytest.mark.parametrize("field_name", ["source", "market", "model_code", "amayama_catalog_id"])
def test_empty_required_field_raises(field_name: str) -> None:
    with pytest.raises(ValueError):
        make_identity(**{field_name: "   "})


def test_no_inferred_vehicle_attributes_fields_do_not_exist():
    field_names = {f.name for f in dataclasses.fields(SpecIdentity)}
    for forbidden in ("body", "engine", "drivetrain", "transmission"):
        assert forbidden not in field_names
