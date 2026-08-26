"""T077 — parse_spec_group_manifest() against real-derived fixtures (Nível B)."""

from pathlib import Path

from amayama_scraper.parsing.spec_group_manifest import parse_spec_group_manifest

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "spec_navigation"


def test_valid_manifest_multi_category_multi_group():
    html = (FIXTURES / "valid_manifest.html").read_text(encoding="utf-8")
    result = parse_spec_group_manifest(html, spec_key="spec-1", source_capture_id="cap-b1")

    assert result.critical_error is None
    manifest = result.manifest
    assert manifest is not None
    assert manifest.manifest_complete is True

    keys = manifest.expected_group_keys()
    assert ("front-axle-steering", "407") in keys
    assert ("front-axle-steering", "409") in keys
    assert ("engine", "100") in keys
    assert ("engine", "103") in keys
    assert ("engine", "105") in keys
    assert len(keys) == 5

    # the non-domain "All" link (data-id="") must never become a category
    slugs = {c.category_slug for c in manifest.categories}
    assert "" not in slugs
    assert slugs == {"front-axle-steering", "engine"}


def test_duplicate_group_id_is_critical_error():
    html = (FIXTURES / "duplicate_group_id.html").read_text(encoding="utf-8")
    result = parse_spec_group_manifest(html, spec_key="spec-2", source_capture_id="cap-b2")

    assert result.critical_error is not None
    assert result.manifest is None


def test_truncated_manifest_is_incomplete_not_critical():
    html = (FIXTURES / "truncated_manifest.html").read_text(encoding="utf-8")
    result = parse_spec_group_manifest(html, spec_key="spec-3", source_capture_id="cap-b3")

    assert result.critical_error is None
    manifest = result.manifest
    assert manifest is not None
    assert manifest.manifest_complete is False
    assert manifest.expected_group_keys() == frozenset()


def test_structural_drift_data_id_vs_url_mismatch_is_critical_error():
    html = (FIXTURES / "structural_drift.html").read_text(encoding="utf-8")
    result = parse_spec_group_manifest(html, spec_key="spec-4", source_capture_id="cap-b4")

    assert result.critical_error is not None
    assert result.manifest is None


def test_parser_version_attached():
    html = (FIXTURES / "valid_manifest.html").read_text(encoding="utf-8")
    result = parse_spec_group_manifest(html, spec_key="spec-1", source_capture_id="cap-b1")
    assert result.parser_version == "amayama-spec-group-manifest-parser-v1"
