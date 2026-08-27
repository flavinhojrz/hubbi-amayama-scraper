"""T090 — structural drift fails explicitly, never permissive parsing (ponto 20 do PLAN)."""

from pathlib import Path

from amayama_scraper.parsing.group_detail import parse_group_detail

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "group_detail"


def test_missing_root_marker_produces_critical_error():
    html = (FIXTURES / "structural_drift.html").read_text()
    result = parse_group_detail(html, category_slug="front-axle-steering", group_id="407")

    assert result.critical_error is not None
    assert result.schemas == ()


def test_missing_schemas_container_produces_critical_error():
    html = """<html><body><div class="epcVariation__details"></div></body></html>"""
    result = parse_group_detail(html, category_slug="front-axle-steering", group_id="407")

    assert result.critical_error is not None
