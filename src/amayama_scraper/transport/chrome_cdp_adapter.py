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

from amayama_scraper.transport.browser_fetch_js import (
    MAX_URLS_PER_SCRIPT_CALL,
    render_batch_fetch_js,
)
from amayama_scraper.transport.errors import (
    ChromeNotReachableError,
    NavigationFailedError,
    NavigationTimeoutError,
    TransportError,
)
from amayama_scraper.transport.port import (
    DEFAULT_BACKOFF_SECONDS,
    DEFAULT_DETAIL_FETCH_CHUNK_SIZE,
    DEFAULT_DETAIL_FETCH_TIMEOUT_MS,
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
    def execute_async_script(self, script: str, *args: object) -> object: ...
    def set_script_timeout(self, time_to_wait: float) -> None: ...


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

    def navigate_many(
        self,
        urls: list[str],
        *,
        chunk_size: int = DEFAULT_DETAIL_FETCH_CHUNK_SIZE,
        timeout_ms: int = DEFAULT_DETAIL_FETCH_TIMEOUT_MS,
    ) -> dict[str, BrowserCapture]:
        if not urls:
            return {}
        js = render_batch_fetch_js(chunk_size=chunk_size, timeout_ms=timeout_ms)
        results: dict[str, BrowserCapture] = {}
        for start in range(0, len(urls), MAX_URLS_PER_SCRIPT_CALL):
            sub_batch = urls[start : start + MAX_URLS_PER_SCRIPT_CALL]
            n_chunks = -(-len(sub_batch) // chunk_size)  # ceil, sem depender de math
            script_timeout_s = n_chunks * (timeout_ms / 1000.0) + 60
            raw = self._fetch_many_with_retry(sub_batch, js, script_timeout_s)
            captured_at = datetime.now(UTC)
            for url, entry in raw.items():
                results[url] = BrowserCapture(
                    page_source=entry["html"],
                    effective_url=entry.get("url") or url,
                    captured_at=captured_at,
                )
        return results

    def _fetch_many_with_retry(
        self, sub_batch: list[str], js: str, script_timeout_s: float
    ) -> dict[str, dict[str, str]]:
        """Retry só para falha de transporte TOTAL do lote (ex.: sessão CDP
        caiu no meio da chamada) — nunca por falha de uma URL individual
        dentro do lote, que já é tratada dentro do próprio JS (AbortController
        por-URL) e simplesmente fica ausente do dict retornado."""
        last_exc: NavigationFailedError | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                self._driver.set_script_timeout(script_timeout_s)
                raw = self._driver.execute_async_script(js, *sub_batch)
                return raw or {}  # type: ignore[return-value]
            except WebDriverException as exc:
                last_exc = NavigationFailedError(
                    f"navigate_many failed for {len(sub_batch)} url(s): {exc}"
                )
                if attempt < self._max_retries:
                    self._sleep(self._backoff_seconds * attempt)
        assert last_exc is not None  # noqa: S101 - loop always sets it before exhausting max_retries >= 1
        raise last_exc

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
