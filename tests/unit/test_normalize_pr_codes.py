"""T106 — normalize_pr_codes(): strip+upper por código, ordenação lexicográfica."""

from amayama_scraper.normalization.pr_codes import normalize_pr_codes


def test_strips_and_uppercases_each_code():
    assert normalize_pr_codes(("  pj1  ", "px1")) == ("PJ1", "PX1")


def test_sorts_lexicographically():
    assert normalize_pr_codes(("PX1", "PJ1", "1BA")) == ("1BA", "PJ1", "PX1")


def test_empty_tuple_stays_empty():
    assert normalize_pr_codes(()) == ()
