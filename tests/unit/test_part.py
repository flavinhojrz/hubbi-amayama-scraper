"""T021 — Part invariants (FR-013, FR-014; data-model.md §3)."""

import pytest

from amayama_scraper.domain.part import Part


def make_part(**overrides: object) -> Part:
    defaults = dict(schema_id="SCH-1", position_pnc="A01")
    defaults.update(overrides)
    return Part(**defaults)  # type: ignore[arg-type]


def test_optional_fields_default_absent():
    part = make_part()
    assert part.oem_code is None
    assert part.description is None
    assert part.details is None
    assert part.period_application_text is None
    assert part.quantity is None
    assert part.image_url is None


def test_pr_codes_defaults_to_empty_tuple():
    part = make_part()
    assert part.pr_codes == ()


def test_absent_optional_field_is_not_an_error():
    part = make_part(oem_code=None, pr_codes=())
    assert part.oem_code is None  # FR-014: absence is not error


def test_pr_codes_preserved_when_present():
    part = make_part(pr_codes=("PR1", "PR2"))
    assert part.pr_codes == ("PR1", "PR2")


@pytest.mark.parametrize("field_name", ["schema_id", "position_pnc"])
def test_required_fields_cannot_be_empty(field_name: str) -> None:
    with pytest.raises(ValueError):
        make_part(**{field_name: ""})
