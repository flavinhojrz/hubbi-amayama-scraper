"""Spike: resolve automático de CAPTCHA (via serviço interno da Hubbi) como
fallback quando o `detect_challenge()` real do projeto acusa bloqueio.

Fluxo testado, por URL:
  1. navigate() na aba já autenticada (mesmo modelo do transporte real,
     attach via CDP a um Chrome já aberto pelo operador).
  2. detect_challenge() real (src/amayama_scraper/validation/detectors/
     challenge.py) decide se é challenge.
  3. Se for: acha a sitekey na página (mesma lógica de captcha_client.py),
     pede resolução pro serviço da Hubbi, aplica o token retornado, relê a
     página e roda detect_challenge() de novo pra confirmar se limpou.

Já confirmado contra uma captura real do projeto (amayama_raw/f2/97/...):
o challenge do Amayama é reCAPTCHA v2 de verdade, com sitekey
`6LfrOVUsAAAAACVda490M8-4gqbiErjfJCQxSl9s` — dentro do que este cliente
sabe resolver. Se um bloqueio for só Cloudflare "Just a moment" (sem
recaptcha), o script reporta isso separado: não tem sitekey pra pedir
resolução, esse tipo o serviço não ajuda.

Não integra nada em src/amayama_scraper — só mede.

Pré-requisitos:
  1. Chrome real já aberto (mesmo do batched_fetch_spike.py):
       & "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" `
           --remote-debugging-port=9222 --user-data-dir="$env:TEMP\\amayama-chrome-spike"
  2. Credencial do serviço via env (NUNCA em arquivo):
       $env:CAPTCHA_API_URL = "https://api-finder-parts.hubbi.app"   # default já é esse
       $env:CAPTCHA_API_TOKEN = "<token real>"

Uso:
    .venv/Scripts/python.exe spikes/captcha_fallback_spike.py --url "https://www.amayama.com/en/genuine-catalogs/epc/volkswagen-overall/golf/<market>"
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from amayama_scraper.transport.chrome_cdp_adapter import (  # noqa: E402
    resolve_cdp_host,
    resolve_cdp_port,
)
from amayama_scraper.validation.detectors.challenge import detect_challenge  # noqa: E402
from captcha_client_adapter import CaptchaClient, CaptchaClientError  # noqa: E402

RESULTS_DIR = Path(__file__).resolve().parent / "results"


@dataclass
class StepTiming:
    label: str
    ms: float


@dataclass
class Outcome:
    url: str
    initial_challenge: bool
    had_sitekey: bool = False
    sitekey: str | None = None
    solved: bool = False
    cleared_after_solve: bool | None = None
    error: str | None = None
    timings: list[StepTiming] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "url": self.url,
            "initial_challenge": self.initial_challenge,
            "had_sitekey": self.had_sitekey,
            "sitekey": self.sitekey,
            "solved": self.solved,
            "cleared_after_solve": self.cleared_after_solve,
            "error": self.error,
            "timings_ms": {t.label: round(t.ms, 1) for t in self.timings},
        }


def attach_driver(host: str, port: int) -> webdriver.Chrome:
    options = Options()
    options.add_experimental_option("debuggerAddress", f"{host}:{port}")
    return webdriver.Chrome(options=options)


def check_current_state(driver: webdriver.Chrome) -> Outcome:
    """Só relê a aba como está agora (sem navegar) — usado depois de uma
    resolução manual de captcha, pra não disparar um challenge novo com um
    navigate() desnecessário."""
    html = driver.page_source
    result = detect_challenge(html)
    outcome = Outcome(url=driver.current_url, initial_challenge=result.detected)
    print(f"Estado atual da aba ({driver.current_url}) -> challenge={result.detected}  evidence={result.evidence}")
    return outcome


def run_one(driver: webdriver.Chrome, url: str, client: CaptchaClient | None) -> Outcome:
    outcome = Outcome(url=url, initial_challenge=False)

    t0 = time.perf_counter()
    driver.get(url)
    html = driver.page_source
    outcome.timings.append(StepTiming("navigate", (time.perf_counter() - t0) * 1000))

    result = detect_challenge(html)
    outcome.initial_challenge = result.detected
    print(f"1) navigate -> challenge={result.detected}  evidence={result.evidence}")

    if not result.detected:
        print("   Sem challenge — nada a resolver.")
        return outcome

    if client is None:
        outcome.error = "sem resolução automática (--no-solve/--manual) — resolva na janela do Chrome e rode de novo com --check-only"
        print(f"   {outcome.error}")
        print(f"   >>> Resolva o captcha manualmente na janela do Chrome (aba em {driver.current_url}) e me avise.")
        return outcome

    t1 = time.perf_counter()
    info = client.detect(driver)
    outcome.timings.append(StepTiming("detect_sitekey", (time.perf_counter() - t1) * 1000))
    sitekey = info.get("sitekey")
    outcome.had_sitekey = bool(sitekey)
    outcome.sitekey = sitekey

    if not sitekey:
        outcome.error = "challenge sem sitekey de recaptcha (provável Cloudflare puro) — este serviço não resolve"
        print(f"2) {outcome.error}")
        return outcome

    print(f"2) sitekey encontrada: {sitekey} (v3={info.get('v3')})")

    try:
        t2 = time.perf_counter()
        token = client.solve(sitekey=sitekey, pageurl=driver.current_url, version="v3" if info.get("v3") else "v2")
        outcome.timings.append(StepTiming("solve_api", (time.perf_counter() - t2) * 1000))
        print(f"3) token recebido do serviço Hubbi em {outcome.timings[-1].ms:.0f}ms")

        t3 = time.perf_counter()
        applied = client.apply(driver, token)
        outcome.timings.append(StepTiming("apply_token", (time.perf_counter() - t3) * 1000))
        print(f"4) token aplicado: campos={applied.get('campos')} callback={applied.get('callback')}")
        outcome.solved = True
    except CaptchaClientError as exc:
        outcome.error = f"falha ao resolver: {exc}"
        print(f"   ERRO: {outcome.error}")
        return outcome

    # dá um tempo pro callback do site processar/redirecionar antes de reler
    time.sleep(3)
    t4 = time.perf_counter()
    html_after = driver.page_source
    outcome.timings.append(StepTiming("reread_after_solve", (time.perf_counter() - t4) * 1000))
    result_after = detect_challenge(html_after)
    outcome.cleared_after_solve = not result_after.detected
    print(
        f"5) releitura pós-resolução -> challenge={result_after.detected}  "
        f"url_atual={driver.current_url}"
    )
    return outcome


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default=None, help="URL real a testar (ex.: página do Golf) — obrigatório exceto com --check-only")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--no-solve", action="store_true", help="só detecta, não chama o serviço de resolução")
    parser.add_argument(
        "--manual",
        action="store_true",
        help="serviço automático da Hubbi indisponível — só navega/detecta/relê, "
        "sem chamar API nenhuma. Resolução é manual (na mesma janela do Chrome).",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="não navega — só relê o estado atual da aba (usar depois de resolver o captcha manualmente)",
    )
    args = parser.parse_args()
    if not args.check_only and not args.url:
        parser.error("--url é obrigatório exceto com --check-only")

    host = resolve_cdp_host(args.host)
    port = resolve_cdp_port(args.port)

    print(f"Conectando via CDP em {host}:{port} (Chrome já aberto, sessão do operador)...")
    driver = attach_driver(host, port)

    if args.check_only:
        outcome = check_current_state(driver)
    else:
        client: CaptchaClient | None = None
        if not args.no_solve and not args.manual:
            try:
                client = CaptchaClient()
                print(f"Serviço de captcha: {client.base_url}")
            except CaptchaClientError as exc:
                print(f"AVISO: {exc}\nRodando só em modo detecção (--no-solve implícito).")

        outcome = run_one(driver, args.url, client)

    print("\n" + "=" * 70)
    print("RESUMO")
    print("=" * 70)
    print(json.dumps(outcome.summary(), indent=2, ensure_ascii=False))

    RESULTS_DIR.mkdir(exist_ok=True)
    out_path = RESULTS_DIR / f"captcha_spike_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    out_path.write_text(json.dumps(outcome.summary(), indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nResultado salvo em {out_path}")


if __name__ == "__main__":
    main()
