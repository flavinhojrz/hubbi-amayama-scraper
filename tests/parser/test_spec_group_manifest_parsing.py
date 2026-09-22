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
    # A single page (even one whose cards happen to cover every declared
    # category) never proves completeness by itself — this fixture in fact
    # declares 3 categories (access-infotainment-miscell has zero cards
    # here, the exact real-world truncation pattern, research.md §21) but
    # even a page that DID show cards for all of them still can't prove it
    # without visiting each category's own URL (bug fix — see
    # orchestration/collection_driver.py::discover_spec_manifest()).
    assert manifest.manifest_complete is False

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

    # declared_category_urls carries every declared category (including the
    # one with zero cards on this page) — what the orchestrator uses to know
    # which categories still need their own dedicated visit.
    declared = manifest.validation_evidence["declared_category_urls"]
    assert set(declared) == {"access-infotainment-miscell", "engine", "front-axle-steering"}


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


def test_category_detail_page_without_nav_parses_with_expected_category_slug():
    """Bug fix (2026-09-10): páginas de UMA categoria específica nunca
    renderizam `.epcVariation__schemaGroups` em produção (confirmado com
    evidência real capturada durante um repair run) — exigi-la
    incondicionalmente fazia toda visita de categoria ser rejeitada, mesmo
    contendo `.epcVariation__schemas` real e válido."""
    html = (FIXTURES / "category_detail_no_nav.html").read_text(encoding="utf-8")
    result = parse_spec_group_manifest(
        html,
        spec_key="spec-5",
        source_capture_id="cap-b5",
        expected_category_slug="access-infotainment-miscell",
    )

    assert result.critical_error is None
    manifest = result.manifest
    assert manifest is not None
    keys = manifest.expected_group_keys()
    assert ("access-infotainment-miscell", "010") in keys
    assert ("access-infotainment-miscell", "012") in keys
    assert len(keys) == 2


def test_category_detail_page_without_nav_and_without_expected_slug_is_critical_error():
    """Sem `expected_category_slug` (rota da página base), a ausência da nav
    continua sendo um erro crítico — só a rota de categoria-específica
    (que já sabe qual categoria está visitando) pode dispensá-la."""
    html = (FIXTURES / "category_detail_no_nav.html").read_text(encoding="utf-8")
    result = parse_spec_group_manifest(html, spec_key="spec-5", source_capture_id="cap-b5")

    assert result.critical_error is not None
    assert result.manifest is None


def test_category_detail_page_card_slug_mismatch_is_still_critical_error():
    """O guard contra drift estrutural continua ativo mesmo sem a nav: um
    card cujo slug (derivado da própria URL do card) diverge do
    `expected_category_slug` pedido pelo chamador ainda é rejeitado."""
    html = (FIXTURES / "category_detail_no_nav.html").read_text(encoding="utf-8")
    result = parse_spec_group_manifest(
        html, spec_key="spec-5", source_capture_id="cap-b5", expected_category_slug="engine"
    )

    assert result.critical_error is not None
    assert result.manifest is None
