"""T062/T073/T076 — INVALID detector, parametrized by capture_kind (FR-010)."""

from pathlib import Path

import pytest

from amayama_scraper.ingestion.capture_kind import CaptureKind
from amayama_scraper.validation.detectors.structure import (
    StructureContractNotAvailableError,
    detect_invalid_structure,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_invalid_structure_fixture_detected_for_group_detail():
    html = (FIXTURES / "invalid_structure.html").read_text()
    result = detect_invalid_structure(html, CaptureKind.GROUP_DETAIL)
    assert result.detected is True


def test_valid_group_detail_structure_not_flagged():
    html = """
    <html><body>
      <div class="epcVariation__details"></div>
      <div class="epcSchema__schemas">
        <div class="epcSchema__schema" data-id="SCH-1">
          <table class="entriesTable"></table>
        </div>
      </div>
    </body></html>
    """
    result = detect_invalid_structure(html, CaptureKind.GROUP_DETAIL)
    assert result.detected is False


def test_valid_market_index_structure_not_flagged():
    html = (FIXTURES / "market_index" / "valid_multi_entry.html").read_text(encoding="utf-8")
    result = detect_invalid_structure(html, CaptureKind.MARKET_INDEX)
    assert result.detected is False


def test_drifted_market_index_structure_flagged():
    html = (FIXTURES / "market_index" / "structural_drift.html").read_text(encoding="utf-8")
    result = detect_invalid_structure(html, CaptureKind.MARKET_INDEX)
    assert result.detected is True


def test_valid_spec_navigation_structure_not_flagged():
    html = (FIXTURES / "spec_navigation" / "valid_manifest.html").read_text(encoding="utf-8")
    result = detect_invalid_structure(html, CaptureKind.SPEC_NAVIGATION)
    assert result.detected is False


def test_structure_check_raises_not_available_for_unmapped_capture_kind() -> None:
    """StructureContractNotAvailableError stays defined as the explicit fallback for
    any capture_kind without a comprovada marker set — never a silent permissive pass."""
    from amayama_scraper.validation.detectors import structure as structure_module

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(structure_module, "_MARKERS_BY_CAPTURE_KIND", {})
        with pytest.raises(StructureContractNotAvailableError):
            detect_invalid_structure("<html></html>", CaptureKind.GROUP_DETAIL)
