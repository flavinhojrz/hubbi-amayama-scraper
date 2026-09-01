"""T003 — BrowserCapture: imutável, campos obrigatórios (data-model.md §1)."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime

import pytest

from amayama_scraper.transport.port import BrowserCapture


def test_browser_capture_holds_page_source_effective_url_and_captured_at() -> None:
    now = datetime.now(UTC)
    capture = BrowserCapture(
        page_source="<html></html>",
        effective_url="https://www.amayama.com/en/genuine-catalogs/epc/foo",
        captured_at=now,
    )
    assert capture.page_source == "<html></html>"
    assert capture.effective_url == "https://www.amayama.com/en/genuine-catalogs/epc/foo"
    assert capture.captured_at is now


def test_browser_capture_is_frozen() -> None:
    capture = BrowserCapture(
        page_source="<html></html>",
        effective_url="https://example.com",
        captured_at=datetime.now(UTC),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        capture.page_source = "<html>mutated</html>"  # type: ignore[misc]


def test_browser_capture_field_names_match_contract() -> None:
    field_names = {f.name for f in dataclasses.fields(BrowserCapture)}
    assert field_names == {"page_source", "effective_url", "captured_at"}
