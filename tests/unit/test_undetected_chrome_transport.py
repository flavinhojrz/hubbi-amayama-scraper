"""UndetectedChromeTransport (transport/undetected_chrome_adapter.py) —
decisão do usuário, 2026-09-10 (substitui DEC-007/Constitution §5 só para
este transporte, ver docstring do módulo).

Todos os testes abaixo injetam `driver_factory` — nenhum Chrome real é
lançado, nenhuma rede real é usada. Mesmo padrão de duplo usado em
`test_chrome_cdp_adapter.py`.
"""

from __future__ import annotations

import pytest
from selenium.common.exceptions import WebDriverException

from amayama_scraper.transport.errors import NavigationFailedError
from amayama_scraper.transport.undetected_chrome_adapter import (
    UndetectedChromeTransport,
    _captcha_client_from_env,
)


class _StubDriver:
    def __init__(self) -> None:
        self.get_calls: list[str] = []
        self.page_source = "<html>stub</html>"
        self.current_url = "https://example.com/stub"
        self.quit_calls = 0
        self.fail_next_get: Exception | None = None
        self.execute_async_script_calls: list[tuple[str, tuple[object, ...]]] = []
        self.execute_async_script_results: list[dict[str, dict[str, str]] | Exception] = []
        self.execute_script_calls: list[tuple[str, tuple[object, ...]]] = []

    def get(self, url: str) -> None:
        self.get_calls.append(url)
        if self.fail_next_get is not None:
            exc, self.fail_next_get = self.fail_next_get, None
            raise exc

    def set_script_timeout(self, time_to_wait: float) -> None:
        pass

    def set_page_load_timeout(self, time_to_wait: float) -> None:
        pass

    def execute_async_script(self, script: str, *args: object) -> object:
        self.execute_async_script_calls.append((script, args))
        if not self.execute_async_script_results:
            raise AssertionError("execute_async_script() called with no queued result")
        result = self.execute_async_script_results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    def execute_script(self, script: str, *args: object) -> object:
        self.execute_script_calls.append((script, args))
        return None

    def quit(self) -> None:
        self.quit_calls += 1


class _FakeCaptchaClient:
    """Duck-typed — só precisa de `solve_on_page(driver)` (o único método
    que `UndetectedChromeTransport` chama)."""

    def __init__(self, token: str | None = None, raises: Exception | None = None) -> None:
        self.token = token
        self.raises = raises
        self.calls: list[object] = []

    def solve_on_page(self, driver: object, **_kwargs: object) -> str | None:
        self.calls.append(driver)
        if self.raises is not None:
            raise self.raises
        return self.token


def _transport(stub: _StubDriver, **kwargs: object) -> UndetectedChromeTransport:
    return UndetectedChromeTransport(driver_factory=lambda: stub, sleep=lambda _s: None, **kwargs)


# --- navigate()/current_capture() básicos -----------------------------------


def test_navigate_calls_driver_get_and_returns_capture() -> None:
    stub = _StubDriver()
    transport = _transport(stub)

    result = transport.navigate("https://www.amayama.com/en/x")

    assert stub.get_calls == ["https://www.amayama.com/en/x"]
    assert result.page_source == "<html>stub</html>"
    assert result.effective_url == "https://example.com/stub"


def test_current_capture_never_navigates() -> None:
    stub = _StubDriver()
    transport = _transport(stub)

    result = transport.current_capture()

    assert stub.get_calls == []
    assert result.effective_url == "https://example.com/stub"


def test_navigate_retries_then_succeeds() -> None:
    stub = _StubDriver()
    stub.fail_next_get = WebDriverException("transient")
    sleeps: list[float] = []
    transport = UndetectedChromeTransport(
        driver_factory=lambda: stub, max_retries=3, backoff_seconds=0.01, sleep=sleeps.append
    )

    result = transport.navigate("https://x/1")

    assert result.effective_url == "https://example.com/stub"
    assert stub.get_calls == ["https://x/1", "https://x/1"]
    assert len(sleeps) == 1


def test_navigate_raises_after_exhausting_retries() -> None:
    class _AlwaysFails(_StubDriver):
        def get(self, url: str) -> None:
            self.get_calls.append(url)
            raise WebDriverException("permanently down")

    stub = _AlwaysFails()
    transport = _transport(stub, max_retries=2, backoff_seconds=0.0)

    with pytest.raises(NavigationFailedError):
        transport.navigate("https://x/1")
    assert len(stub.get_calls) == 2


# --- navigate_many(): mesmo fetch em lote de chrome_cdp_adapter.py ---------


def test_navigate_many_returns_a_browser_capture_per_url() -> None:
    stub = _StubDriver()
    stub.execute_async_script_results.append(
        {"https://x/1": {"html": "<html>one</html>", "url": "https://x/1"}}
    )
    transport = _transport(stub)

    result = transport.navigate_many(["https://x/1"])

    assert result["https://x/1"].page_source == "<html>one</html>"


def test_navigate_many_empty_urls_never_calls_driver() -> None:
    stub = _StubDriver()
    transport = _transport(stub)

    assert transport.navigate_many([]) == {}
    assert stub.execute_async_script_calls == []


# --- resolução automática de captcha ----------------------------------------


def test_navigate_calls_captcha_client_and_waits_when_token_returned() -> None:
    stub = _StubDriver()
    captcha = _FakeCaptchaClient(token="solved-token")
    sleeps: list[float] = []
    transport = UndetectedChromeTransport(
        driver_factory=lambda: stub, captcha_client=captcha, sleep=sleeps.append
    )

    transport.navigate("https://x/challenge")

    assert captcha.calls == [stub]
    assert sleeps == [2.0]  # dá tempo do callback do site reagir


def test_navigate_never_touches_captcha_client_when_none_configured() -> None:
    stub = _StubDriver()
    transport = UndetectedChromeTransport(driver_factory=lambda: stub, captcha_client=None)

    # nenhuma leitura de DOM/rede é tentada — comportamento idêntico a antes
    # de existir CaptchaClient (challenge fica na tela, sem tentativa).
    transport.navigate("https://x/1")
    transport.current_capture()

    assert stub.execute_script_calls == []


def test_captcha_client_error_never_crashes_navigation() -> None:
    stub = _StubDriver()
    from amayama_scraper.transport.captcha_client import CaptchaClientError

    captcha = _FakeCaptchaClient(raises=CaptchaClientError("service unavailable"))
    transport = UndetectedChromeTransport(driver_factory=lambda: stub, captcha_client=captcha)

    result = transport.navigate("https://x/1")  # never raises

    assert result.page_source == "<html>stub</html>"
    assert captcha.calls == [stub]


def test_captcha_client_unexpected_exception_never_crashes_navigation() -> None:
    stub = _StubDriver()
    captcha = _FakeCaptchaClient(raises=RuntimeError("boom"))
    transport = UndetectedChromeTransport(driver_factory=lambda: stub, captcha_client=captcha)

    result = transport.navigate("https://x/1")  # never raises

    assert result.page_source == "<html>stub</html>"


def test_navigate_never_waits_when_no_token_was_returned() -> None:
    stub = _StubDriver()
    captcha = _FakeCaptchaClient(token=None)  # nenhuma sitekey na página
    sleeps: list[float] = []
    transport = UndetectedChromeTransport(
        driver_factory=lambda: stub, captcha_client=captcha, sleep=sleeps.append
    )

    transport.navigate("https://x/1")

    assert sleeps == []


# --- close() -----------------------------------------------------------------


def test_close_quits_the_driver() -> None:
    stub = _StubDriver()
    transport = _transport(stub)

    transport.close()

    assert stub.quit_calls == 1


def test_close_never_raises_even_if_quit_fails() -> None:
    class _FailsToQuit(_StubDriver):
        def quit(self) -> None:
            raise WebDriverException("already dead")

    stub = _FailsToQuit()
    transport = _transport(stub)

    transport.close()  # never raises


# --- _captcha_client_from_env() ---------------------------------------------


def test_captcha_client_from_env_is_none_without_both_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CAPTCHA_API_URL", raising=False)
    monkeypatch.delenv("TOKEN_API", raising=False)
    assert _captcha_client_from_env() is None


def test_captcha_client_from_env_is_none_with_only_one_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CAPTCHA_API_URL", "http://127.0.0.1:8060")
    monkeypatch.delenv("TOKEN_API", raising=False)
    assert _captcha_client_from_env() is None


def test_captcha_client_from_env_is_built_when_both_variables_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CAPTCHA_API_URL", "http://127.0.0.1:8060")
    monkeypatch.setenv("TOKEN_API", "secret-token")
    client = _captcha_client_from_env()
    assert client is not None
    assert client.base_url == "http://127.0.0.1:8060"
    assert client.api_token == "secret-token"
