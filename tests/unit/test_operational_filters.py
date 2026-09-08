"""T076/T086/T091 — apply_operational_filters()/apply_group_limit() (FR-023
a FR-025, FR-009). Operam sobre identidade JÁ descoberta, nunca alteram a
descoberta em si; --spec inexistente entre as descobertas é erro explícito,
nunca silenciosamente ignorado nem inventado."""

from __future__ import annotations

from datetime import date

import pytest

from amayama_scraper.domain.identity import SpecIdentity
from amayama_scraper.orchestration.collection_driver import (
    OperationalFilters,
    UnknownSpecFilterError,
    apply_group_limit,
    apply_operational_filters,
)


def _identity(catalog_id: str) -> SpecIdentity:
    return SpecIdentity(
        source="AMAYAMA",
        manufacturer="VOLKSWAGEN",
        vehicle_model="AMAROK",
        market="AMA-BR",
        model_code="S7BC8A",
        amayama_catalog_id=catalog_id,
        production_period_raw="2022.06 - ...",
        source_url=f"https://x/{catalog_id}",
        production_start=date(2022, 6, 1),
    )


_A, _B, _C = _identity("1"), _identity("2"), _identity("3")


def test_no_filters_returns_all_identities_unchanged() -> None:
    result = apply_operational_filters([_A, _B, _C], OperationalFilters())
    assert result == [_A, _B, _C]


def test_limit_specs_truncates() -> None:
    result = apply_operational_filters([_A, _B, _C], OperationalFilters(limit_specs=2))
    assert result == [_A, _B]


def test_spec_filter_restricts_to_discovered_keys() -> None:
    result = apply_operational_filters(
        [_A, _B, _C], OperationalFilters(spec_filter=[_B.stable_key()])
    )
    assert result == [_B]


def test_spec_filter_with_multiple_keys_preserves_original_order() -> None:
    result = apply_operational_filters(
        [_A, _B, _C], OperationalFilters(spec_filter=[_C.stable_key(), _A.stable_key()])
    )
    assert result == [_A, _C]


def test_unknown_spec_filter_raises_explicit_error_never_invents_a_spec() -> None:
    with pytest.raises(UnknownSpecFilterError):
        apply_operational_filters(
            [_A, _B], OperationalFilters(spec_filter=["not-a-real-stable-key"])
        )


def test_apply_group_limit_none_returns_unchanged() -> None:
    pending = [("engine", "100"), ("body", "800")]
    assert apply_group_limit(pending, None) == pending


def test_apply_group_limit_truncates_deterministically() -> None:
    pending = [("engine", "100"), ("body", "800"), ("front-axle-steering", "407")]
    assert apply_group_limit(pending, 2) == [("engine", "100"), ("body", "800")]


def test_apply_group_limit_zero_returns_empty() -> None:
    pending = [("engine", "100")]
    assert apply_group_limit(pending, 0) == []
