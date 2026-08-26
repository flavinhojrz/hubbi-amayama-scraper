"""T023 — OemReference derivation (research.md §11)."""

from amayama_scraper.domain.hierarchy import Schema
from amayama_scraper.domain.oem_reference import derive_oem_reference
from amayama_scraper.domain.part import Part


def test_derives_distinct_oem_codes_sorted():
    schema = Schema(
        schema_id="SCH-1",
        parts=(
            Part(schema_id="SCH-1", position_pnc="A1", oem_code="B2"),
            Part(schema_id="SCH-1", position_pnc="A2", oem_code="A1"),
            Part(schema_id="SCH-1", position_pnc="A3", oem_code="B2"),  # duplicate
        ),
    )
    ref = derive_oem_reference(schema)
    assert ref.schema_id == "SCH-1"
    assert ref.oem_codes == ("A1", "B2")


def test_ignores_parts_without_oem_code():
    schema = Schema(
        schema_id="SCH-1",
        parts=(
            Part(schema_id="SCH-1", position_pnc="A1", oem_code=None),
            Part(schema_id="SCH-1", position_pnc="A2", oem_code="X1"),
        ),
    )
    ref = derive_oem_reference(schema)
    assert ref.oem_codes == ("X1",)


def test_empty_schema_produces_no_codes():
    schema = Schema(schema_id="SCH-1")
    ref = derive_oem_reference(schema)
    assert ref.oem_codes == ()


def test_never_invents_codes_not_present_in_parts():
    schema = Schema(
        schema_id="SCH-1", parts=(Part(schema_id="SCH-1", position_pnc="A1", oem_code="ONLY"),)
    )
    ref = derive_oem_reference(schema)
    assert set(ref.oem_codes) == {"ONLY"}
