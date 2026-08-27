"""T074 — parse_market_spec_index() against real-derived fixtures (Nível A)."""

from datetime import date
from pathlib import Path

from amayama_scraper.parsing.market_index import parse_market_spec_index

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "market_index"


def test_valid_multi_entry():
    html = (FIXTURES / "valid_multi_entry.html").read_text(encoding="utf-8")
    result = parse_market_spec_index(html, source_capture_id="cap-1")

    assert result.critical_error is None
    assert len(result.entries) == 5
    assert all(e.market == "AMA-BR" for e in result.entries)

    first = result.entries[0]
    assert first.model_code == "AGDA43"
    assert first.amayama_catalog_id == "62158"
    assert first.grade == "Trendline"
    assert (
        first.source_url
        == "https://www.amayama.com/en/genuine-catalogs/epc/volkswagen-overall/amarok/ama-br/agda43-62158"
    )


def test_same_model_code_diff_catalog_id():
    html = (FIXTURES / "same_model_code_diff_catalog.html").read_text(encoding="utf-8")
    result = parse_market_spec_index(html, source_capture_id="cap-2")

    assert result.critical_error is None
    assert len(result.entries) == 2
    assert all(e.model_code == "S7BC8A" for e in result.entries)
    catalog_ids = {e.amayama_catalog_id for e in result.entries}
    assert catalog_ids == {"62184", "61189"}

    by_catalog = {e.amayama_catalog_id: e for e in result.entries}
    assert by_catalog["62184"].production_period_raw == "2022.06 - ..."
    assert by_catalog["61189"].production_period_raw == "2019.08 - 2022.05"


def test_open_ended_period_maps_to_none_end():
    html = (FIXTURES / "open_ended_period.html").read_text(encoding="utf-8")
    result = parse_market_spec_index(html, source_capture_id="cap-3")

    assert result.critical_error is None
    entry = result.entries[0]
    assert entry.production_period_raw == "2024.04 - ..."
    assert entry.production_start == date(2024, 4, 1)
    assert entry.production_end is None


def test_missing_optional_grade_is_not_an_error():
    html = (FIXTURES / "missing_optional_field.html").read_text(encoding="utf-8")
    result = parse_market_spec_index(html, source_capture_id="cap-4")

    assert result.critical_error is None
    assert len(result.parse_errors) == 0
    entry = result.entries[0]
    assert entry.grade is None
    assert entry.configuration is None


def test_structural_drift_produces_critical_error():
    html = (FIXTURES / "structural_drift.html").read_text(encoding="utf-8")
    result = parse_market_spec_index(html, source_capture_id="cap-5")

    assert result.critical_error is not None
    assert result.entries == ()


def test_parser_version_attached():
    html = (FIXTURES / "valid_multi_entry.html").read_text(encoding="utf-8")
    result = parse_market_spec_index(html, source_capture_id="cap-1")
    assert result.parser_version == "amayama-market-index-parser-v1"
