"""UndetectedChromeTransport — Chrome PRÓPRIO por instância (`undetected_chromedriver`,
com resolução automática de reCAPTCHA via `captcha_client.py`).

Decisão explícita do usuário (2026-09-10, substitui DEC-007/Constitution §5
de `002-amarok-ama-br-browser-scraper` para este transporte): ao contrário
de `chrome_cdp_adapter.py` (que só ANEXA a um Chrome já aberto pelo
operador, nunca resolve challenge, sempre espera um humano), este adapter
LANÇA seu próprio Chrome (perfil copiado do Chrome real do operador, para
herdar a sessão/cookies já autenticados) e tenta resolver automaticamente
qualquer reCAPTCHA encontrado via um serviço externo (`CaptchaClient`) —
modelado no scraper irmão que já usa esse padrão contra outros sites
(main.py/captcha_client.py do mesmo operador).

Quando `CAPTCHA_API_URL`/`TOKEN_API` não estão configurados,
`self._captcha_client` é `None` e nenhuma tentativa de resolução automática
acontece — o comportamento cai para "challenge fica na tela, aguardando
resolução manual na janela visível", igual a `chrome_cdp_adapter.py`.

Implementa o mesmo `BrowserTransport` (transport/port.py) que
`ChromeCdpTransport` — `navigate_many()` usa exatamente o mesmo fetch em
lote (`transport/browser_fetch_js.py`, credentials:'include', validado em
spikes/batched_fetch_spike.py), a técnica que já reduz challenge de
~90-100% para ~0% nesse tipo de requisição — este adapter reduz a fonte
restante (a navegação real, ~90-100% de challenge por si só) resolvendo
automaticamente em vez de depender de operador presente.

Junto com `chrome_cdp_adapter.py`, é o único arquivo de `src/amayama_scraper`
autorizado a importar Selenium/`undetected_chromedriver`
(`tests/unit/test_no_browser_automation_dependency.py`).
"""

from __future__ import annotations

import contextlib
import logging
import os
import platform
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

import setuptools  # noqa: F401 - restores `distutils` (Python 3.12+) before uc imports it below
import undetected_chromedriver as uc
from selenium.common.exceptions import WebDriverException

from amayama_scraper.transport.browser_fetch_js import (
    MAX_URLS_PER_SCRIPT_CALL,
    render_batch_fetch_js,
)
from amayama_scraper.transport.captcha_client import CaptchaClient, CaptchaClientError
from amayama_scraper.transport.errors import (
    ChromeLaunchFailedError,
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

logger = logging.getLogger(__name__)

_PAGE_LOAD_TIMEOUT_SECONDS = 60
_SCRIPT_TIMEOUT_SECONDS = 60
_DRIVER_START_RETRIES = 5
_DRIVER_START_RETRY_DELAY_SECONDS = 3.0
#: Cache dirs pesados que nunca precisam ser copiados junto com um perfil
#: real do Chrome — mesma lista usada pelo scraper irmão (main.py).
_PROFILE_CACHE_DIRS_TO_SKIP = {
    "Cache",
    "Code Cache",
    "Crashpad",
    "BrowserMetrics",
    "component_crx_cache",
    "DawnGraphiteCache",
    "DawnWebGPUCache",
    "GraphiteDawnCache",
    "GPUCache",
    "GrShaderCache",
    "Safe Browsing",
    "ShaderCache",
    "Session Storage",
    "blob_storage",
    "optimization_guide_model_store",
    "optimization_guide_hint_cache_store",
    "segmentation_platform",
}


class _UndetectedDriverLike(Protocol):
    page_source: str
    current_url: str

    def get(self, url: str) -> None: ...
    def execute_async_script(self, script: str, *args: object) -> object: ...
    def execute_script(self, script: str, *args: object) -> object: ...
    def set_script_timeout(self, time_to_wait: float) -> None: ...
    def set_page_load_timeout(self, time_to_wait: float) -> None: ...
    def quit(self) -> None: ...


def find_chrome_binary() -> str | None:
    system = platform.system()
    if system == "Windows":
        candidates = [
            Path(os.environ.get("PROGRAMW6432", r"C:\Program Files"))
            / "Google"
            / "Chrome"
            / "Application"
            / "chrome.exe",
            Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
            / "Google"
            / "Chrome"
            / "Application"
            / "chrome.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
            / "Google"
            / "Chrome"
            / "Application"
            / "chrome.exe",
            Path(os.environ.get("LOCALAPPDATA", ""))
            / "Google"
            / "Chrome"
            / "Application"
            / "chrome.exe",
        ]
    elif system == "Darwin":
        candidates = [Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")]
    else:
        candidates = [
            Path("/usr/bin/google-chrome"),
            Path("/usr/bin/google-chrome-stable"),
            Path("/usr/bin/chromium-browser"),
            Path("/usr/bin/chromium"),
            Path("/snap/bin/chromium"),
        ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def find_chrome_profile_source() -> Path:
    system = platform.system()
    if system == "Windows":
        return Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data"
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "Google" / "Chrome"
    return Path.home() / ".config" / "google-chrome"


def _ignore_profile_cache_dirs(_dir: str, names: list[str]) -> list[str]:
    return [name for name in names if name in _PROFILE_CACHE_DIRS_TO_SKIP]


def ensure_profile_copy(source: Path, dest: Path) -> Path | None:
    """Copia (uma vez, cacheado em `dest`) o perfil real do Chrome do
    operador — herdar cookies/sessão já autenticada reduz a chance de cair
    em challenge logo na primeira navegação. `None` quando não há perfil
    real detectável (segue sem herdar nada, perfil limpo)."""
    if dest.exists():
        return dest
    if not source.exists():
        return None
    shutil.copytree(source, dest, ignore=_ignore_profile_cache_dirs)
    return dest


def _chrome_major_version(chrome_binary: str | None) -> int | None:
    if not chrome_binary or not os.path.exists(chrome_binary):
        return None
    try:
        if platform.system() == "Windows":
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    f"(Get-Item '{chrome_binary}').VersionInfo.ProductVersion",
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=15,
            )
        else:
            result = subprocess.run(
                [chrome_binary, "--version"],
                capture_output=True,
                text=True,
                check=False,
                timeout=15,
            )
        output = (result.stdout or result.stderr or "").strip()
        head = output.split(".", 1)[0].split()[-1] if output else ""
        return int(head) if head.isdigit() else None
    except Exception:  # noqa: BLE001 - best-effort only, never blocks driver creation
        return None


@dataclass(frozen=True, slots=True)
class ProfileConfig:
    """Como o perfil do Chrome é herdado/isolado por instância deste
    transporte — `None` em qualquer campo desliga aquele comportamento
    (nunca lança exceção)."""

    profile_cache_dir: Path | None = None
    #: Diretório onde a cópia (uma vez) do perfil real fica cacheada.
    real_profile_source: Path | None = None
    #: Perfil real do Chrome do operador (herda sessão/cookies).


def _default_profile_config() -> ProfileConfig:
    return ProfileConfig(
        profile_cache_dir=Path.cwd() / "chrome_profile",
        real_profile_source=find_chrome_profile_source(),
    )


def _create_session_profile(base_profile: Path) -> Path:
    session_profile = Path(tempfile.mkdtemp(prefix="amayama_chrome_"))
    shutil.copytree(base_profile, session_profile, dirs_exist_ok=True)
    return session_profile


def create_driver(
    *,
    headless: bool = False,
    chrome_binary: str | None = None,
    profile_config: ProfileConfig | None = None,
    retries: int = _DRIVER_START_RETRIES,
    retry_delay: float = _DRIVER_START_RETRY_DELAY_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
) -> _UndetectedDriverLike:
    """Lança um Chrome PRÓPRIO via `undetected_chromedriver` — nunca anexa a
    um processo existente (isso é `chrome_cdp_adapter.py`). Cada chamada usa
    uma cópia isolada (tempdir) do perfil cacheado, para nunca disputar lock
    de perfil com um Chrome que o operador já tenha aberto."""
    binary = chrome_binary if chrome_binary is not None else find_chrome_binary()
    cfg = profile_config if profile_config is not None else _default_profile_config()

    profile_copy: Path | None = None
    if cfg.profile_cache_dir is not None and cfg.real_profile_source is not None:
        profile_copy = ensure_profile_copy(cfg.real_profile_source, cfg.profile_cache_dir)

    chrome_version = _chrome_major_version(binary)

    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        session_profile = _create_session_profile(profile_copy) if profile_copy else None

        options = uc.ChromeOptions()
        options.page_load_strategy = "eager"
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        if headless:
            options.add_argument("--headless=new")
        if binary:
            options.binary_location = binary

        driver_kwargs: dict[str, object] = {
            "options": options,
            "headless": headless,
            "use_subprocess": True,
        }
        if binary:
            driver_kwargs["browser_executable_path"] = binary
        if session_profile is not None:
            driver_kwargs["user_data_dir"] = str(session_profile)
        if chrome_version is not None:
            driver_kwargs["version_main"] = chrome_version

        try:
            driver: _UndetectedDriverLike = uc.Chrome(**driver_kwargs)
            driver.set_page_load_timeout(_PAGE_LOAD_TIMEOUT_SECONDS)
            driver.set_script_timeout(_SCRIPT_TIMEOUT_SECONDS)
            return driver
        except Exception as exc:  # noqa: BLE001 - undetected_chromedriver raises broadly
            last_error = exc
            logger.warning(
                "Falha ao iniciar Chrome (tentativa %d/%d): %s", attempt, retries, str(exc)[:200]
            )
            if session_profile is not None:
                shutil.rmtree(session_profile, ignore_errors=True)
            if attempt < retries:
                sleep(retry_delay)

    raise ChromeLaunchFailedError(
        f"could not start undetected_chromedriver after {retries} attempt(s): {last_error}"
    ) from last_error


class UndetectedChromeTransport:
    """`BrowserTransport` que lança e é dono do seu próprio Chrome (uma
    instância por worker — `--workers N` produz N Chromes independentes,
    exatamente como `ChromeCdpTransport` produz N conexões CDP a N portas)."""

    def __init__(
        self,
        *,
        headless: bool = False,
        chrome_binary: str | None = None,
        profile_config: ProfileConfig | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
        captcha_client: CaptchaClient | None = None,
        driver_factory: Callable[[], _UndetectedDriverLike] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._max_retries = max_retries
        self._backoff_seconds = backoff_seconds
        self._sleep = sleep
        # `None` (default) => auto-detecta CAPTCHA_API_URL/TOKEN_API; quando
        # nenhum dos dois está configurado, nunca tenta resolver nada
        # automaticamente (mesmo comportamento de sempre: challenge fica na
        # tela, aguardando o operador).
        self._captcha_client = (
            captcha_client if captcha_client is not None else _captcha_client_from_env()
        )
        factory = (
            driver_factory
            if driver_factory is not None
            else (
                lambda: create_driver(
                    headless=headless,
                    chrome_binary=chrome_binary,
                    profile_config=profile_config,
                    sleep=sleep,
                )
            )
        )
        self._driver = factory()

    def close(self) -> None:
        with contextlib.suppress(Exception):  # best-effort cleanup, never raises
            self._driver.quit()

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
            n_chunks = -(-len(sub_batch) // chunk_size)
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
        assert last_exc is not None  # noqa: S101
        raise last_exc

    def _navigate_once(self, url: str) -> BrowserCapture:
        try:
            self._driver.get(url)
        except WebDriverException as exc:
            raise NavigationFailedError(f"navigation to {url!r} failed: {exc}") from exc
        # _read_current() já chama _maybe_solve_captcha() — nunca duplicar a
        # tentativa aqui (chamaria o serviço externo duas vezes pela mesma
        # página).
        return self._read_current()

    def _read_current(self) -> BrowserCapture:
        self._maybe_solve_captcha()
        try:
            page_source = self._driver.page_source
            effective_url = self._driver.current_url
        except WebDriverException as exc:
            raise NavigationFailedError(f"failed to read current page state: {exc}") from exc
        return BrowserCapture(
            page_source=page_source, effective_url=effective_url, captured_at=datetime.now(UTC)
        )

    def _maybe_solve_captcha(self) -> None:
        """Chamada barata quando não há `CaptchaClient` configurado (`None`,
        sem nenhuma leitura de DOM). Quando há, roda `solve_on_page()` — que
        por si só só faz rede se encontrar uma sitekey real na página — e
        nunca deixa uma falha do serviço externo derrubar a navegação
        (challenge sem solução automática apenas permanece na tela, como
        antes de existir esse cliente)."""
        if self._captcha_client is None:
            return
        try:
            token = self._captcha_client.solve_on_page(self._driver)
        except CaptchaClientError as exc:
            logger.warning("Captcha: serviço externo não resolveu: %s", exc)
            return
        except Exception as exc:  # noqa: BLE001 - never let the solver crash navigation
            logger.warning("Captcha: erro inesperado ao tentar resolver: %s", exc)
            return
        if token:
            # dá tempo do callback do site reagir (recarregar conteúdo,
            # redirecionar) antes da próxima leitura de página.
            self._sleep(2.0)

    def _with_retry(self, action: Callable[[], BrowserCapture]) -> BrowserCapture:
        last_exc: TransportError | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                return action()
            except (NavigationFailedError, NavigationTimeoutError) as exc:
                last_exc = exc
                if attempt < self._max_retries:
                    self._sleep(self._backoff_seconds * attempt)
        assert last_exc is not None  # noqa: S101
        raise last_exc


def _captcha_client_from_env() -> CaptchaClient | None:
    """`CaptchaClient` só é construído quando as duas variáveis de ambiente
    estão presentes — sem isso, `None` (nenhuma tentativa de resolução
    automática, comportamento idêntico a `chrome_cdp_adapter.py`)."""
    base_url = os.environ.get("CAPTCHA_API_URL")
    api_token = os.environ.get("TOKEN_API")
    if not base_url or not api_token:
        return None
    return CaptchaClient(base_url=base_url, api_token=api_token)


__all__ = [
    "ProfileConfig",
    "UndetectedChromeTransport",
    "create_driver",
    "ensure_profile_copy",
    "find_chrome_binary",
    "find_chrome_profile_source",
]
