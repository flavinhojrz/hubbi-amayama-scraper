"""T014/T016/T018/T020/T022 — ChromeCdpTransport (research.md §2-§4, §10; DEC-007).

Todos os testes abaixo usam stubs — nenhum Chrome real é aberto, nenhuma
rede real é usada. `selenium.webdriver.chrome.options.Options` é a única
classe real do Selenium instanciada aqui (é um objeto de configuração puro,
sem I/O) — `webdriver.Chrome` é sempre substituído por uma factory stub.
"""

from __future__ import annotations

import urllib.error

import pytest
from selenium.common.exceptions import WebDriverException

from amayama_scraper.transport.chrome_cdp_adapter import (
    DEFAULT_CDP_HOST,
    DEFAULT_CDP_PORT,
    ChromeCdpTransport,
    resolve_cdp_host,
    resolve_cdp_port,
)
from amayama_scraper.transport.errors import ChromeNotReachableError, NavigationFailedError

# --- T014: resolução de endereço CDP ---------------------------------------


def test_resolve_cdp_host_prefers_explicit_over_env_and_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AMAYAMA_CDP_HOST", "10.0.0.5")
    assert resolve_cdp_host("192.168.1.1") == "192.168.1.1"


def test_resolve_cdp_host_falls_back_to_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AMAYAMA_CDP_HOST", "10.0.0.5")
    assert resolve_cdp_host(None) == "10.0.0.5"


def test_resolve_cdp_host_falls_back_to_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AMAYAMA_CDP_HOST", raising=False)
    assert resolve_cdp_host(None) == DEFAULT_CDP_HOST


def test_resolve_cdp_port_prefers_explicit_over_env_and_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AMAYAMA_CDP_PORT", "9333")
    assert resolve_cdp_port(9999) == 9999


def test_resolve_cdp_port_falls_back_to_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AMAYAMA_CDP_PORT", "9333")
    assert resolve_cdp_port(None) == 9333


def test_resolve_cdp_port_falls_back_to_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AMAYAMA_CDP_PORT", raising=False)
    assert resolve_cdp_port(None) == DEFAULT_CDP_PORT


# --- stubs compartilhados ----------------------------------------------------


class _StubDriver:
    def __init__(self) -> None:
        self.get_calls: list[str] = []
        self.page_source = "<html>stub</html>"
        self.current_url = "https://example.com/stub"
        self.fail_next_get: Exception | None = None

    def get(self, url: str) -> None:
        self.get_calls.append(url)
        if self.fail_next_get is not None:
            exc, self.fail_next_get = self.fail_next_get, None
            raise exc


def _reachable_urlopen(*_args: object, **_kwargs: object) -> object:
    class _Resp:
        def __enter__(self) -> _Resp:
            return self

        def __exit__(self, *exc: object) -> None:
            return None

    return _Resp()


def _unreachable_urlopen(*_args: object, **_kwargs: object) -> object:
    raise urllib.error.URLError("connection refused")


# --- T016: fail-fast quando Chrome não está acessível -----------------------


def test_construction_raises_chrome_not_reachable_without_calling_webdriver_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "amayama_scraper.transport.chrome_cdp_adapter.urllib.request.urlopen", _unreachable_urlopen
    )
    factory_calls: list[object] = []

    def factory(**kwargs: object) -> _StubDriver:
        factory_calls.append(kwargs)
        return _StubDriver()

    with pytest.raises(ChromeNotReachableError):
        ChromeCdpTransport(host="127.0.0.1", port=9222, webdriver_factory=factory)
    assert factory_calls == []  # never attempts to launch/attach when unreachable


# --- T018: navigate() usa debuggerAddress, nunca lança Chrome ---------------


def test_navigate_attaches_via_debugger_address_never_launches_chrome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "amayama_scraper.transport.chrome_cdp_adapter.urllib.request.urlopen", _reachable_urlopen
    )
    captured_options: list[object] = []
    stub = _StubDriver()

    def factory(**kwargs: object) -> _StubDriver:
        captured_options.append(kwargs["options"])
        return stub

    transport = ChromeCdpTransport(host="127.0.0.1", port=9222, webdriver_factory=factory)
    result = transport.navigate("https://www.amayama.com/en/genuine-catalogs/epc/x")

    assert stub.get_calls == ["https://www.amayama.com/en/genuine-catalogs/epc/x"]
    assert result.page_source == "<html>stub</html>"
    assert result.effective_url == "https://example.com/stub"
    (options,) = captured_options
    assert options.experimental_options["debuggerAddress"] == "127.0.0.1:9222"


# --- T020: current_capture() relê sem nova navegação ------------------------


def test_current_capture_does_not_call_driver_get(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "amayama_scraper.transport.chrome_cdp_adapter.urllib.request.urlopen", _reachable_urlopen
    )
    stub = _StubDriver()
    transport = ChromeCdpTransport(
        host="127.0.0.1", port=9222, webdriver_factory=lambda **_kw: stub
    )

    result = transport.current_capture()

    assert stub.get_calls == []  # no navigation issued
    assert result.effective_url == "https://example.com/stub"


# --- T022: retry interno configurável de falha de transporte ----------------


def test_navigate_retries_configurable_times_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "amayama_scraper.transport.chrome_cdp_adapter.urllib.request.urlopen", _reachable_urlopen
    )
    stub = _StubDriver()
    sleeps: list[float] = []
    transport = ChromeCdpTransport(
        host="127.0.0.1",
        port=9222,
        webdriver_factory=lambda **_kw: stub,
        max_retries=3,
        backoff_seconds=0.01,
        sleep=sleeps.append,
    )
    stub.fail_next_get = WebDriverException("transient network blip")

    result = transport.navigate("https://x/1")

    assert result.effective_url == "https://example.com/stub"
    assert stub.get_calls == [
        "https://x/1",
        "https://x/1",
    ]  # first attempt failed, second succeeded
    assert len(sleeps) == 1


def test_navigate_raises_navigation_failed_after_exhausting_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "amayama_scraper.transport.chrome_cdp_adapter.urllib.request.urlopen", _reachable_urlopen
    )

    class _AlwaysFailingDriver(_StubDriver):
        def get(self, url: str) -> None:
            self.get_calls.append(url)
            raise WebDriverException("permanently down")

    stub = _AlwaysFailingDriver()
    transport = ChromeCdpTransport(
        host="127.0.0.1",
        port=9222,
        webdriver_factory=lambda **_kw: stub,
        max_retries=2,
        backoff_seconds=0.0,
        sleep=lambda _s: None,
    )

    with pytest.raises(NavigationFailedError):
        transport.navigate("https://x/1")
    assert len(stub.get_calls) == 2  # exactly max_retries attempts, no more
