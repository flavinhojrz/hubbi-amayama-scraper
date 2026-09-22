"""Cliente do resolvedor de reCAPTCHA, para uso dentro de `undetected_chrome_adapter.py`.

Adaptado de um cliente equivalente já em uso noutro scraper do mesmo
operador — mesmo ciclo pedir/esperar/aplicar, só com o import de logging
trocado (`src.core.logging_config` não existe neste projeto) para o
`logging` padrão.

O navegador do scraper NAO precisa de nenhuma extensão: quem tem a
integração com o serviço de resolução é o serviço externo (`CAPTCHA_API_URL`)
e o Chrome dele. Daqui sai apenas o pedido (sitekey + pageurl) e volta o
token, que é injetado na página como se o usuário tivesse resolvido.

    from amayama_scraper.transport.captcha_client import CaptchaClient

    client = CaptchaClient()
    token = client.solve_on_page(driver)   # detecta, resolve e injeta

`CaptchaClient` só é construído/usado quando `CAPTCHA_API_URL`+`TOKEN_API`
estão configurados (`undetected_chrome_adapter.py`) — sem isso, nenhuma
captura de sitekey/chamada de rede é feita, e um challenge continua exigindo
intervenção manual do operador na janela visível, exatamente como antes.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)

_DEFAULT_BASE = os.getenv("CAPTCHA_API_URL", "http://127.0.0.1:8060")
_DEFAULT_TOKEN = os.getenv("TOKEN_API", "")

# Le a sitekey da pagina, cobrindo os tres jeitos de o widget aparecer:
# atributo no HTML, iframe ja renderizado (parametro `k`) e v3 (?render=).
_DETECT_SITEKEY = """
const porAtributo = [...document.querySelectorAll('[data-sitekey]')]
  .map((element) => element.dataset.sitekey);
const porIframe = [...document.querySelectorAll('iframe[src*="recaptcha"]')]
  .map((frame) => {
    try { return new URL(frame.src).searchParams.get('k'); } catch (e) { return null; }
  });
const porScript = [...document.scripts]
  .map((script) => script.src)
  .filter((src) => src.includes('recaptcha/api.js') || src.includes('recaptcha/enterprise.js'))
  .map((src) => {
    try { return new URL(src).searchParams.get('render'); } catch (e) { return null; }
  })
  .filter((value) => value && value !== 'explicit');

const sitekey = [...porAtributo, ...porIframe, ...porScript].find(Boolean) || null;
return { sitekey: sitekey, v3: porScript.length > 0 && porIframe.length === 0 };
"""

# Aplica o token. Preencher o textarea nao basta na maioria dos sites: eles
# reagem ao CALLBACK do widget, nao ao valor do campo. Por isso procuramos o
# callback em tres lugares, do mais explicito ao mais escondido.
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

// 1. data-callback no proprio elemento, apontando para uma funcao global.
const elemento = document.querySelector('[data-callback]');
const nomeGlobal = elemento && elemento.getAttribute('data-callback');
if (nomeGlobal && typeof window[nomeGlobal] === 'function') {
  try { window[nomeGlobal](token); callbackChamado = true; } catch (e) {}
}

// 2. O callback guardado pelo proprio grecaptcha ao renderizar o widget.
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
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token
        self.poll_interval = poll_interval
        self.timeout = timeout

    # -- API --------------------------------------------------------------

    def solve(
        self,
        sitekey: str,
        pageurl: str,
        *,
        version: str = "v2",
        action: str = "verify",
        invisible: bool = False,
        enterprise: bool = False,
    ) -> str:
        """Pede o token e espera. Consulta em vez de segurar a conexão.

        Segurar seria mais curto de escrever e quebraria atrás de qualquer
        proxy: 60s de `proxy_read_timeout` cortam antes de boa parte das
        resoluções, e o token de um captcha já resolvido se perde no 504.
        """
        headers = {"Authorization": self.api_token, "Content-Type": "application/json"}
        payload: dict[str, Any] = {
            "sitekey": sitekey,
            "pageurl": pageurl,
            "version": version,
            "action": action,
            "invisible": invisible,
            "enterprise": enterprise,
        }

        resposta = requests.post(
            f"{self.base_url}/captcha/solve",
            json=payload,
            headers=headers,
            timeout=30,
        )
        resposta.raise_for_status()
        tarefa = resposta.json()

        if tarefa.get("token"):
            return str(tarefa["token"])

        return self._aguardar(str(tarefa["id"]), headers)

    def _aguardar(self, task_id: str, headers: dict[str, str]) -> str:
        limite = time.monotonic() + self.timeout

        while time.monotonic() < limite:
            time.sleep(self.poll_interval)

            resposta = requests.get(
                f"{self.base_url}/captcha/result/{task_id}",
                headers=headers,
                timeout=30,
            )
            resposta.raise_for_status()
            tarefa = resposta.json()

            if tarefa.get("status") == "ready" and tarefa.get("token"):
                return str(tarefa["token"])

            if tarefa.get("status") == "failed":
                raise CaptchaClientError(tarefa.get("error") or "captcha não resolvido")

        raise CaptchaClientError(f"o captcha {task_id} não ficou pronto em {self.timeout:.0f}s")

    # -- Navegador ----------------------------------------------------------

    @staticmethod
    def detect(driver: Any) -> dict[str, Any]:
        """A sitekey e a versão do captcha presente na página aberta."""
        return driver.execute_script(_DETECT_SITEKEY) or {}

    @staticmethod
    def apply(driver: Any, token: str) -> dict[str, Any]:
        """Injeta o token e dispara o callback do site.

        O widget continua com o quadrado desmarcado na tela — o token vive no
        campo, não no desenho. Esperar o "visto" aparecer é procurar sinal
        onde ele não existe.
        """
        return driver.execute_script(_APPLY_TOKEN, token) or {}

    def solve_on_page(self, driver: Any, **kwargs: Any) -> str | None:
        """Detecta o captcha da página aberta, resolve e injeta o token.

        Devolve o token aplicado, ou `None` quando não há captcha na página
        (chamada barata — só roda uma leitura de DOM, nenhuma requisição de
        rede acontece sem uma sitekey detectada)."""
        encontrado = self.detect(driver)
        sitekey = encontrado.get("sitekey")

        if not sitekey:
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
