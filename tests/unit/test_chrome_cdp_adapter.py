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
        self.execute_async_script_calls: list[tuple[str, tuple[object, ...]]] = []
        self.script_timeouts: list[float] = []
        self.execute_async_script_results: list[dict[str, dict[str, str]] | Exception] = []

    def get(self, url: str) -> None:
        self.get_calls.append(url)
        if self.fail_next_get is not None:
            exc, self.fail_next_get = self.fail_next_get, None
            raise exc

    def set_script_timeout(self, time_to_wait: float) -> None:
        self.script_timeouts.append(time_to_wait)

    def execute_async_script(self, script: str, *args: object) -> object:
        self.execute_async_script_calls.append((script, args))
        if not self.execute_async_script_results:
            raise AssertionError("execute_async_script() called with no queued result")
        result = self.execute_async_script_results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


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


# --- navigate_many(): fetch em lote via execute_async_script ----------------
# spikes/batched_fetch_spike.py — validado empiricamente contra o Amayama
# real: ~5.900 requisições, 0 challenges em modo lote vs. ~90-100% em modo
# navigate único.


def _transport(
    monkeypatch: pytest.MonkeyPatch, stub: _StubDriver, **kwargs: object
) -> ChromeCdpTransport:
    monkeypatch.setattr(
        "amayama_scraper.transport.chrome_cdp_adapter.urllib.request.urlopen", _reachable_urlopen
    )
    return ChromeCdpTransport(
        host="127.0.0.1", port=9222, webdriver_factory=lambda **_kw: stub, **kwargs
    )


def test_navigate_many_returns_a_browser_capture_per_url(monkeypatch: pytest.MonkeyPatch) -> None:
    stub = _StubDriver()
    stub.execute_async_script_results.append(
        {
            "https://x/1": {"html": "<html>one</html>", "url": "https://x/1"},
            "https://x/2": {"html": "<html>two</html>", "url": "https://x/2"},
        }
    )
    transport = _transport(monkeypatch, stub)

    result = transport.navigate_many(["https://x/1", "https://x/2"])

    assert set(result) == {"https://x/1", "https://x/2"}
    assert result["https://x/1"].page_source == "<html>one</html>"
    assert result["https://x/1"].effective_url == "https://x/1"
    assert result["https://x/2"].page_source == "<html>two</html>"


def test_navigate_many_uses_response_url_when_server_redirected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """r.url (pós-redirect) popula effective_url — nunca a URL pedida, quando
    diferem (ex.: servidor redirecionou pra uma página de challenge)."""
    stub = _StubDriver()
    stub.execute_async_script_results.append(
        {"https://x/1": {"html": "<html>redirected</html>", "url": "https://x/captcha.html"}}
    )
    transport = _transport(monkeypatch, stub)

    result = transport.navigate_many(["https://x/1"])

    assert result["https://x/1"].effective_url == "https://x/captcha.html"


def test_navigate_many_url_missing_from_result_is_simply_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Uma URL que falhou/deu timeout/veio vazia dentro do lote nunca levanta
    — só fica ausente do dict, pro chamador reprocessar via navigate()."""
    stub = _StubDriver()
    stub.execute_async_script_results.append(
        {"https://x/1": {"html": "<html>ok</html>", "url": "https://x/1"}}
    )
    transport = _transport(monkeypatch, stub)

    result = transport.navigate_many(["https://x/1", "https://x/2"])

    assert set(result) == {"https://x/1"}


def test_navigate_many_empty_urls_never_calls_driver(monkeypatch: pytest.MonkeyPatch) -> None:
    stub = _StubDriver()
    transport = _transport(monkeypatch, stub)

    result = transport.navigate_many([])

    assert result == {}
    assert stub.execute_async_script_calls == []


def test_navigate_many_embeds_chunk_size_and_timeout_into_the_script(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub = _StubDriver()
    stub.execute_async_script_results.append({})
    transport = _transport(monkeypatch, stub)

    transport.navigate_many(["https://x/1"], chunk_size=5, timeout_ms=12_345)

    (script, args) = stub.execute_async_script_calls[0]
    assert "var BATCH = 5;" in script
    assert "var TIMEOUT = 12345;" in script
    assert args == ("https://x/1",)


def test_navigate_many_retries_configurable_times_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub = _StubDriver()
    stub.execute_async_script_results = [
        WebDriverException("transient network blip"),
        {"https://x/1": {"html": "<html>ok</html>", "url": "https://x/1"}},
    ]
    sleeps: list[float] = []
    transport = _transport(
        monkeypatch, stub, max_retries=3, backoff_seconds=0.01, sleep=sleeps.append
    )

    result = transport.navigate_many(["https://x/1"])

    assert result["https://x/1"].page_source == "<html>ok</html>"
    assert len(stub.execute_async_script_calls) == 2
    assert len(sleeps) == 1


def test_navigate_many_raises_navigation_failed_after_exhausting_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub = _StubDriver()
    stub.execute_async_script_results = [
        WebDriverException("permanently down"),
        WebDriverException("permanently down"),
    ]
    transport = _transport(
        monkeypatch, stub, max_retries=2, backoff_seconds=0.0, sleep=lambda _s: None
    )

    with pytest.raises(NavigationFailedError):
        transport.navigate_many(["https://x/1"])
    assert len(stub.execute_async_script_calls) == 2  # exactly max_retries attempts, no more


def test_navigate_many_splits_large_batches_into_multiple_script_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Uma única chamada execute_async_script com muitas URLs estoura o
    timeout do cliente HTTP do Selenium (bug encontrado em
    spikes/batched_fetch_spike.py) — navigate_many() sub-batela
    internamente, sempre abaixo do limite, de forma transparente pro
    chamador (o resultado final é um único dict com tudo)."""
    stub = _StubDriver()
    urls = [f"https://x/{i}" for i in range(151)]  # > _MAX_URLS_PER_SCRIPT_CALL (150)
    stub.execute_async_script_results = [
        {url: {"html": f"<html>{i}</html>", "url": url} for i, url in enumerate(urls[:150])},
        {urls[150]: {"html": "<html>150</html>", "url": urls[150]}},
    ]
    transport = _transport(monkeypatch, stub)

    result = transport.navigate_many(urls)

    assert len(stub.execute_async_script_calls) == 2
    assert len(result) == 151
