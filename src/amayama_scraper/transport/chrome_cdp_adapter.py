"""ChromeCdpTransport — único adapter que fala Selenium/CDP (research.md §2-§4, §10; DEC-007).

Attach via `debuggerAddress` a um Chrome real já aberto pelo operador —
NUNCA lança/gerencia um processo de Chrome. Falha ao conectar é fail-fast
(`ChromeNotReachableError`, sem tentativa de lançar Chrome como fallback).
Retry interno cobre apenas falha de transporte transitória (research.md
§10) — nunca decide outcome de validação, nunca resolve CAPTCHA, nunca usa
técnicas de evasão de detecção, rotação de rede, ou manipulação de
cookies/tokens (Constitution §5, DEC-007).

Este é o ÚNICO arquivo de `src/amayama_scraper` autorizado a importar
`selenium` (verificado por `tests/unit/test_no_browser_automation_dependency.py`).
"""

from __future__ import annotations

import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.options import Options

from amayama_scraper.transport.errors import (
    ChromeNotReachableError,
    NavigationFailedError,
    NavigationTimeoutError,
    TransportError,
)
from amayama_scraper.transport.port import (
    DEFAULT_BACKOFF_SECONDS,
    DEFAULT_MAX_RETRIES,
    BrowserCapture,
)

DEFAULT_CDP_HOST = "127.0.0.1"
DEFAULT_CDP_PORT = 9222

_CDP_ENV_HOST = "AMAYAMA_CDP_HOST"
_CDP_ENV_PORT = "AMAYAMA_CDP_PORT"


def resolve_cdp_host(explicit: str | None) -> str:
    """Precedência: argumento explícito > env `AMAYAMA_CDP_HOST` > default (research.md §3)."""
    if explicit is not None:
        return explicit
    return os.environ.get(_CDP_ENV_HOST, DEFAULT_CDP_HOST)


def resolve_cdp_port(explicit: int | None) -> int:
    """Precedência: argumento explícito > env `AMAYAMA_CDP_PORT` > default (research.md §3)."""
    if explicit is not None:
        return explicit
    env_value = os.environ.get(_CDP_ENV_PORT)
    if env_value is not None:
        return int(env_value)
    return DEFAULT_CDP_PORT


class _SeleniumDriverLike(Protocol):
    page_source: str
    current_url: str

    def get(self, url: str) -> None: ...


class ChromeCdpTransport:
    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        *,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
        webdriver_factory: Callable[..., _SeleniumDriverLike] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._host = resolve_cdp_host(host)
        self._port = resolve_cdp_port(port)
        self._max_retries = max_retries
        self._backoff_seconds = backoff_seconds
        self._sleep = sleep
        self._check_reachable()

        options = Options()
        options.add_experimental_option("debuggerAddress", f"{self._host}:{self._port}")
        factory = webdriver_factory if webdriver_factory is not None else webdriver.Chrome
        self._driver = factory(options=options)

    def _check_reachable(self) -> None:
        url = f"http://{self._host}:{self._port}/json/version"
        try:
            urllib.request.urlopen(url, timeout=5)  # noqa: S310
        except (urllib.error.URLError, OSError) as exc:
            raise ChromeNotReachableError(
                f"Chrome DevTools endpoint {url} unreachable: {exc}. "
                "Abra um Chrome real com --remote-debugging-port antes de rodar o scraper "
                "(quickstart.md 'Pré-requisitos') — este adapter nunca lança um Chrome "
                "por conta própria."
            ) from exc

    def navigate(self, url: str) -> BrowserCapture:
        return self._with_retry(lambda: self._navigate_once(url))

    def current_capture(self) -> BrowserCapture:
        return self._with_retry(self._read_current)

    def _navigate_once(self, url: str) -> BrowserCapture:
        try:
            self._driver.get(url)
        except WebDriverException as exc:
            raise NavigationFailedError(f"navigation to {url!r} failed: {exc}") from exc
        return self._read_current()

    def _read_current(self) -> BrowserCapture:
        try:
            page_source = self._driver.page_source
            effective_url = self._driver.current_url
        except WebDriverException as exc:
            raise NavigationFailedError(f"failed to read current page state: {exc}") from exc
        return BrowserCapture(
            page_source=page_source, effective_url=effective_url, captured_at=datetime.now(UTC)
        )

    def _with_retry(self, action: Callable[[], BrowserCapture]) -> BrowserCapture:
        last_exc: TransportError | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                return action()
            except (NavigationFailedError, NavigationTimeoutError) as exc:
                last_exc = exc
                if attempt < self._max_retries:
                    self._sleep(self._backoff_seconds * attempt)
        assert last_exc is not None  # noqa: S101 - loop always sets it before exhausting max_retries >= 1
        raise last_exc


__all__ = [
    "DEFAULT_BACKOFF_SECONDS",
    "DEFAULT_CDP_HOST",
    "DEFAULT_CDP_PORT",
    "DEFAULT_MAX_RETRIES",
    "ChromeCdpTransport",
    "resolve_cdp_host",
    "resolve_cdp_port",
]
