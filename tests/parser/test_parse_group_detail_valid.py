"""T084 — parse_group_detail() happy path against valid fixture."""

from pathlib import Path

from amayama_scraper.parsing.group_detail import PARSER_VERSION, parse_group_detail

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "group_detail"


def test_parses_schemas_and_parts():
    html = (FIXTURES / "valid_group_detail.html").read_text()
    result = parse_group_detail(html, category_slug="front-axle-steering", group_id="407")

    assert result.critical_error is None
    assert result.category_slug == "front-axle-steering"
    assert result.group_id == "407"
    assert len(result.schemas) == 1

    schema = result.schemas[0]
    assert schema.schema_id == "SCH-1"
    assert len(schema.parts) == 2

    first = schema.parts[0]
    assert first.position_pnc == "A01"
    assert first.oem_code == "1K0407151"
    assert first.description == "Control arm"
    assert first.details == "left side, front"
    assert first.period_application_text == "08.2010-12.2015"
    assert first.quantity == "1"
    assert first.image_url == "https://cdn.example/sch-1.jpg"


def test_parser_version_attached():
    html = (FIXTURES / "valid_group_detail.html").read_text()
    result = parse_group_detail(html, category_slug="front-axle-steering", group_id="407")
    assert result.parser_version == PARSER_VERSION == "amayama-parser-v1"
