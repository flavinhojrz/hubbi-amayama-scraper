"""T049 — RawCaptureInput contract (contracts/input-contracts.md §1).

T024 (002) — AcquisitionMode.AUTOMATED_BROWSER_CDP tem paridade total com
MANUAL_BROWSER: nenhuma ramificação de comportamento depende do valor
específico de acquisition_mode (data-model.md §0, research.md §6).
"""

from datetime import UTC, datetime

import pytest

from amayama_scraper.ingestion.capture_input import RawCaptureInput
from amayama_scraper.ingestion.capture_kind import AcquisitionMode, CaptureKind


def make_input(**overrides: object) -> RawCaptureInput:
    defaults: dict[str, object] = dict(
        capture_kind=CaptureKind.GROUP_DETAIL,
        source_url="https://amayama.example/group/407",
        collected_at=datetime(2026, 8, 26, tzinfo=UTC),
        raw_content=b"<html>content</html>",
        run_id="run-1",
    )
    defaults.update(overrides)
    return RawCaptureInput(**defaults)  # type: ignore[arg-type]


def test_valid_input_constructs():
    capture = make_input()
    assert capture.capture_kind is CaptureKind.GROUP_DETAIL


def test_relative_url_rejected():
    with pytest.raises(ValueError):
        make_input(source_url="/relative/path")


def test_empty_raw_content_rejected_as_invalid_before_validation():
    with pytest.raises(ValueError):
        make_input(raw_content=b"")


@pytest.mark.parametrize("kind", list(CaptureKind))
def test_all_three_capture_kinds_valid(kind: CaptureKind) -> None:
    capture = make_input(capture_kind=kind)
    assert capture.capture_kind is kind


def test_empty_run_id_rejected():
    with pytest.raises(ValueError):
        make_input(run_id="")


def test_automated_browser_cdp_acquisition_mode_exists_and_is_accepted() -> None:
    capture = make_input(acquisition_mode=AcquisitionMode.AUTOMATED_BROWSER_CDP)
    assert capture.acquisition_mode is AcquisitionMode.AUTOMATED_BROWSER_CDP


def test_automated_browser_cdp_behaves_identically_to_manual_browser() -> None:
    manual = make_input(acquisition_mode=AcquisitionMode.MANUAL_BROWSER)
    automated = make_input(acquisition_mode=AcquisitionMode.AUTOMATED_BROWSER_CDP)
    # Only acquisition_mode itself differs — no other field is affected by the value.
    assert manual.raw_content == automated.raw_content
    assert manual.capture_kind == automated.capture_kind
    assert manual.source_url == automated.source_url
