"""T111 — canonical JSON serialization determinism (research.md §7)."""

from amayama_scraper.fingerprints.canonical import canonical_json, domain_hash, multiset_counts


def test_canonical_json_sorts_keys_regardless_of_insertion_order():
    a = canonical_json({"b": 1, "a": 2})
    b = canonical_json({"a": 2, "b": 1})
    assert a == b == '{"a":2,"b":1}'


def test_canonical_json_is_compact_no_extra_whitespace():
    assert canonical_json({"a": [1, 2]}) == '{"a":[1,2]}'


def test_canonical_json_escapes_non_ascii():
    out = canonical_json({"a": "café"})
    assert "café" not in out
    assert "\\u00e9" in out


def test_domain_hash_deterministic():
    payload = {"x": 1, "y": "z"}
    h1 = domain_hash("amayama:test:v1\0", payload)
    h2 = domain_hash("amayama:test:v1\0", payload)
    assert h1 == h2
    assert len(h1) == 64  # sha256 hex digest


def test_domain_hash_changes_with_separator():
    payload = {"x": 1}
    h1 = domain_hash("amayama:test:v1\0", payload)
    h2 = domain_hash("amayama:test:v2\0", payload)
    assert h1 != h2


def test_domain_hash_changes_with_payload():
    h1 = domain_hash("sep\0", {"x": 1})
    h2 = domain_hash("sep\0", {"x": 2})
    assert h1 != h2


def test_multiset_counts_order_irrelevant_duplicates_matter():
    a = multiset_counts(["x", "y", "x"])
    b = multiset_counts(["y", "x", "x"])
    assert a == b == [("x", 2), ("y", 1)]


def test_multiset_counts_distinguishes_different_multiplicities():
    a = multiset_counts(["x", "x"])
    b = multiset_counts(["x"])
    assert a != b
