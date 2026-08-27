"""T104 — schema_id trim + pnc trim+upper."""

from amayama_scraper.normalization.identifiers import normalize_pnc, normalize_schema_id


def test_normalize_schema_id_strips_only():
    assert normalize_schema_id("  407 - wishbone  ") == "407 - wishbone"


def test_normalize_pnc_strips_and_uppercases():
    assert normalize_pnc("  a01  ") == "A01"
