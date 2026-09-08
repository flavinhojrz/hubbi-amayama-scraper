"""T005 — BrowserTransport: Protocol estrutural (contracts/browser-transport-contract.md §1)."""

from __future__ import annotations

from datetime import UTC, datetime

from amayama_scraper.transport.port import BrowserCapture, BrowserTransport


class _MinimalTransport:
    """Objeto mínimo que satisfaz BrowserTransport estruturalmente, sem herdar dele."""

    def navigate(self, url: str) -> BrowserCapture:
        return BrowserCapture(
            page_source="<html></html>", effective_url=url, captured_at=datetime.now(UTC)
        )

    def current_capture(self) -> BrowserCapture:
        return BrowserCapture(
            page_source="<html></html>",
            effective_url="https://example.com",
            captured_at=datetime.now(UTC),
        )


def _accepts_transport(transport: BrowserTransport) -> BrowserCapture:
    return transport.navigate("https://example.com")


def test_minimal_object_satisfies_browser_transport_protocol() -> None:
    transport: BrowserTransport = _MinimalTransport()
    capture = _accepts_transport(transport)
    assert capture.effective_url == "https://example.com"


def test_protocol_exposes_exactly_navigate_and_current_capture() -> None:
    members = {name for name in dir(BrowserTransport) if not name.startswith("_")}
    assert members == {"navigate", "current_capture"}
