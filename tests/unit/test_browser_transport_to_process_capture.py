"""T072 — to_raw_capture_input(): BrowserCapture -> RawCaptureInput sem
transformação (data-model.md §1, FR-005).

Nota de sequenciamento: implementado antes de T073/T074 conforme
formalmente numerado em tasks.md porque T055 (Fase 6, await_challenge_resolution)
depende desta conversão — ambos vivem no mesmo arquivo
orchestration/collection_driver.py, construído incrementalmente.
"""

from __future__ import annotations

from datetime import UTC, datetime

from amayama_scraper.domain.identity import ExpectedIdentityContext
from amayama_scraper.ingestion.capture_kind import AcquisitionMode, CaptureKind
from amayama_scraper.orchestration.collection_driver import to_raw_capture_input
from amayama_scraper.transport.port import BrowserCapture


def test_to_raw_capture_input_preserves_page_source_byte_for_byte() -> None:
    capture = BrowserCapture(
        page_source="<html>épica</html>",
        effective_url="https://www.amayama.com/en/genuine-catalogs/epc/x",
        captured_at=datetime(2026, 8, 28, tzinfo=UTC),
    )
    result = to_raw_capture_input(capture, capture_kind=CaptureKind.GROUP_DETAIL, run_id="run-1")

    assert result.raw_content == capture.page_source.encode("utf-8")
    assert result.source_url == capture.effective_url
    assert result.collected_at == capture.captured_at
    assert result.run_id == "run-1"
    assert result.capture_kind is CaptureKind.GROUP_DETAIL


def test_to_raw_capture_input_uses_automated_browser_cdp_acquisition_mode() -> None:
    capture = BrowserCapture(
        page_source="<html></html>", effective_url="https://x", captured_at=datetime.now(UTC)
    )
    result = to_raw_capture_input(capture, capture_kind=CaptureKind.MARKET_INDEX, run_id="run-1")
    assert result.acquisition_mode is AcquisitionMode.AUTOMATED_BROWSER_CDP


def test_to_raw_capture_input_passes_through_expected_identity_context() -> None:
    capture = BrowserCapture(
        page_source="<html></html>", effective_url="https://x", captured_at=datetime.now(UTC)
    )
    context = ExpectedIdentityContext(market="AMA-BR", model_code="S7BC8A")
    result = to_raw_capture_input(
        capture,
        capture_kind=CaptureKind.SPEC_NAVIGATION,
        run_id="run-1",
        expected_identity_context=context,
    )
    assert result.expected_identity_context == context


def test_to_raw_capture_input_defaults_expected_identity_context_to_none() -> None:
    capture = BrowserCapture(
        page_source="<html></html>", effective_url="https://x", captured_at=datetime.now(UTC)
    )
    result = to_raw_capture_input(capture, capture_kind=CaptureKind.MARKET_INDEX, run_id="run-1")
    assert result.expected_identity_context is None
