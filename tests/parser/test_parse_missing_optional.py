"""T086 — missing optional fields are ABSENT, never an error (FR-014)."""

from pathlib import Path

from amayama_scraper.parsing.group_detail import parse_group_detail
from amayama_scraper.parsing.results import FieldStatus

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "group_detail"


def test_missing_fields_marked_absent_not_error():
    html = (FIXTURES / "missing_optional_fields.html").read_text()
    result = parse_group_detail(html, category_slug="front-axle-steering", group_id="407")

    assert result.critical_error is None
    assert len(result.parse_errors) == 0

    part = result.schemas[0].parts[0]
    assert part.position_pnc == "A01"
    assert part.oem_code is None
    assert part.field_status["oem_code"] is FieldStatus.ABSENT
    assert part.field_status["description"] is FieldStatus.ABSENT
    assert part.field_status["pr_codes"] is FieldStatus.ABSENT
