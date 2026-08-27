"""T082 — ParsedGroupDetail/ParsedSchema/ParsedPart + field_status semantics."""

from amayama_scraper.parsing.results import (
    FieldStatus,
    ParsedGroupDetail,
    ParsedPart,
    ParsedSchema,
    ParseError,
)


def test_field_status_three_values():
    assert {v.value for v in FieldStatus} == {"PRESENT", "ABSENT", "PARSE_ERROR"}


def test_parsed_part_tracks_field_status_per_field():
    part = ParsedPart(
        schema_id="SCH-1",
        position_pnc="A01",
        field_status={"oem_code": FieldStatus.ABSENT, "description": FieldStatus.PRESENT},
        description="Front bushing",
    )
    assert part.field_status["oem_code"] is FieldStatus.ABSENT
    assert part.field_status["description"] is FieldStatus.PRESENT


def test_to_part_projects_to_domain_part():
    part = ParsedPart(schema_id="SCH-1", position_pnc="A01", oem_code="X1")
    domain_part = part.to_part()
    assert domain_part.schema_id == "SCH-1"
    assert domain_part.oem_code == "X1"


def test_group_detail_holds_schemas_and_errors():
    detail = ParsedGroupDetail(
        category_slug="front-axle-steering",
        group_id="407",
        schemas=(ParsedSchema(schema_id="SCH-1", parts=()),),
        parse_errors=(ParseError(message="minor issue"),),
        critical_error=None,
    )
    assert detail.critical_error is None
    assert len(detail.parse_errors) == 1
    assert detail.schemas[0].schema_id == "SCH-1"
