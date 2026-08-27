"""T088 — empty Group (schema with zero parts) is valid and preserved (data-model.md §2)."""

from pathlib import Path

from amayama_scraper.parsing.group_detail import parse_group_detail

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "group_detail"


def test_empty_group_preserved_not_error():
    html = (FIXTURES / "empty_group.html").read_text()
    result = parse_group_detail(html, category_slug="front-axle-steering", group_id="407")

    assert result.critical_error is None
    assert len(result.schemas) == 1
    assert result.schemas[0].parts == ()
