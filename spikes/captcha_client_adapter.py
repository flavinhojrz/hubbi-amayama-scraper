"""Porta local de `captcha_client.py` (raiz do projeto) só pra rodar dentro
deste spike, sem editar o arquivo original que você colou como referência.

Dois ajustes de encaixe, comportamento idêntico ao original:
  1. `from src.core.logging_config import logger` (import de outro repo,
     não existe aqui) -> logging padrão da stdlib.
  2. `requests` (não é dependência deste projeto) -> `urllib.request`
     (stdlib), pra não precisar instalar nada só pro spike.

O resto (detecção de sitekey, aplicação de token, polling) é a mesma
lógica, mesmos textos de log.

NUNCA hardcoda o token de autenticação aqui nem em nenhum outro arquivo do
repo — sempre lido de env (CAPTCHA_API_TOKEN / TOKEN_API).
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger("captcha_client_adapter")

_DEFAULT_BASE = os.getenv("CAPTCHA_API_URL", "https://api-finder-parts.hubbi.app")
_DEFAULT_TOKEN = os.getenv("CAPTCHA_API_TOKEN") or os.getenv("TOKEN_API", "")

_DETECT_SITEKEY = """
const porAtributo = [...document.querySelectorAll('[data-sitekey]')]
  .map((element) => element.dataset.sitekey);
const porIframe = [...document.querySelectorAll('iframe[src*="recaptcha"]')]
  .map((frame) => { try { return new URL(frame.src).searchParams.get('k'); } catch (e) { return null; } });
const porScript = [...document.scripts]
  .map((script) => script.src)
  .filter((src) => src.includes('recaptcha/api.js') || src.includes('recaptcha/enterprise.js'))
  .map((src) => { try { return new URL(src).searchParams.get('render'); } catch (e) { return null; } })
  .filter((value) => value && value !== 'explicit');

const sitekey = [...porAtributo, ...porIframe, ...porScript].find(Boolean) || null;
return { sitekey: sitekey, v3: porScript.length > 0 && porIframe.length === 0 };
"""

_APPLY_TOKEN = """
const token = arguments[0];
let campos = 0;

document.querySelectorAll('textarea[name="g-recaptcha-response"], #g-recaptcha-response')
  .forEach((campo) => {
    campo.value = token;
    campo.innerHTML = token;
    campos += 1;
  });

let callbackChamado = false;

const elemento = document.querySelector('[data-callback]');
const nomeGlobal = elemento && elemento.getAttribute('data-callback');
if (nomeGlobal && typeof window[nomeGlobal] === 'function') {
  try { window[nomeGlobal](token); callbackChamado = true; } catch (e) {}
}

if (!callbackChamado && window.___grecaptcha_cfg && window.___grecaptcha_cfg.clients) {
  const visitar = (objeto, profundidade) => {
    if (!objeto || callbackChamado || profundidade > 4) return;
    for (const chave of Object.keys(objeto)) {
      let valor;
      try { valor = objeto[chave]; } catch (e) { continue; }
      if (typeof valor === 'function' && /callback/i.test(chave)) {
        try { valor(token); callbackChamado = true; return; } catch (e) {}
      } else if (valor && typeof valor === 'object') {
        visitar(valor, profundidade + 1);
      }
    }
  };
  for (const cliente of Object.values(window.___grecaptcha_cfg.clients)) {
    visitar(cliente, 0);
  }
}

return { campos: campos, callback: callbackChamado };
"""


class CaptchaClientError(RuntimeError):
    """O serviço não devolveu token."""


class CaptchaClient:
    def __init__(
        self,
        base_url: str = _DEFAULT_BASE,
        api_token: str = _DEFAULT_TOKEN,
        poll_interval: float = 3.0,
        timeout: float = 240.0,
    ) -> None:
        if not api_token:
            raise CaptchaClientError(
                "Falta o token do serviço de captcha. Setar CAPTCHA_API_TOKEN "
                "(ou TOKEN_API) antes de rodar — nunca hardcoded em arquivo."
            )
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token
        self.poll_interval = poll_interval
        self.timeout = timeout

    # -- HTTP (stdlib, sem `requests`) ----------------------------------------

    def _request(self, method: str, path: str, payload: dict | None = None) -> dict:
        url = f"{self.base_url}{path}"
        headers = {"Authorization": self.api_token, "Content-Type": "application/json"}
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise CaptchaClientError(f"HTTP {exc.code} de {url}: {body[:300]}") from exc
        except urllib.error.URLError as exc:
            raise CaptchaClientError(f"Falha de conexão com {url}: {exc}") from exc

    # -- API --------------------------------------------------------------

    def solve(
        self,
        sitekey: str,
        pageurl: str,
        *,
        version: str = "v2",
        invisible: bool = False,
        enterprise: bool = False,
    ) -> str:
        payload = {
            "sitekey": sitekey,
            "pageurl": pageurl,
            "version": version,
            "invisible": invisible,
            "enterprise": enterprise,
            "wait": True,
        }
        tarefa = self._request("POST", "/captcha/solve", payload)

        if tarefa.get("token"):
            return str(tarefa["token"])

        if tarefa.get("id"):
            return self._aguardar(str(tarefa["id"]))

        raise CaptchaClientError(f"resposta inesperada do serviço: {tarefa}")

    def _aguardar(self, task_id: str) -> str:
        limite = time.monotonic() + self.timeout
        while time.monotonic() < limite:
            time.sleep(self.poll_interval)
            tarefa = self._request("GET", f"/captcha/result/{task_id}")
            if tarefa.get("status") == "ready" and tarefa.get("token"):
                return str(tarefa["token"])
            if tarefa.get("status") == "failed":
                raise CaptchaClientError(tarefa.get("error") or "captcha nao resolvido")
        raise CaptchaClientError(f"o captcha {task_id} nao ficou pronto em {self.timeout:.0f}s")

    # -- Navegador ------------------------------------------------------------

    @staticmethod
    def detect(driver: Any) -> dict[str, Any]:
        return driver.execute_script(_DETECT_SITEKEY) or {}

    @staticmethod
    def apply(driver: Any, token: str) -> dict[str, Any]:
        return driver.execute_script(_APPLY_TOKEN, token) or {}

    def solve_on_page(self, driver: Any, **kwargs: Any) -> str | None:
        encontrado = self.detect(driver)
        sitekey = encontrado.get("sitekey")

        if not sitekey:
            logger.info("Captcha: nenhuma sitekey na pagina %s", driver.current_url)
            return None

        logger.info("Captcha: sitekey %s detectada em %s", sitekey[:14], driver.current_url)

        token = self.solve(
            sitekey=sitekey,
            pageurl=driver.current_url,
            version="v3" if encontrado.get("v3") else "v2",
            **kwargs,
        )

        aplicado = self.apply(driver, token)
        logger.info(
            "Captcha: token aplicado em %s campo(s), callback=%s",
            aplicado.get("campos"),
            aplicado.get("callback"),
        )
        return token
