"""Spike: valida se fetch() batelado disparado via execute_async_script no
Chrome já autenticado (técnica de main.py) é mais rápido e não aumenta a
taxa de bloqueio Cloudflare/CAPTCHA, comparado ao navigate() sequencial que
o transporte real (ChromeCdpTransport) usa hoje.

NÃO integra nada em src/amayama_scraper. Só mede. Attach via CDP a um
Chrome já aberto pelo operador (mesmo modelo do adapter real) — nunca
lança Chrome próprio, nunca copia perfil, nunca usa undetected_chromedriver.

Pré-requisito (mesmo do projeto real, specs/002.../quickstart.md):
    & "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" `
        --remote-debugging-port=9222 --user-data-dir="$env:TEMP\\amayama-chrome-spike"
E logar manualmente em amayama.com / resolver qualquer CAPTCHA inicial nessa
janela antes de rodar o spike, do jeito que o operador já faz para o scraper
real (specs/002-.../quickstart.md "Pré-requisitos").

Uso:
    .venv/Scripts/python.exe spikes/batched_fetch_spike.py --mode both --limit 24
    .venv/Scripts/python.exe spikes/batched_fetch_spike.py --mode batch --limit 24 --chunk-size 5
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from amayama_scraper.transport.chrome_cdp_adapter import (  # noqa: E402
    resolve_cdp_host,
    resolve_cdp_port,
)
from amayama_scraper.validation.detectors.challenge import detect_challenge  # noqa: E402

DEFAULT_DB_PATH = PROJECT_ROOT / "amayama.db"
RESULTS_DIR = Path(__file__).resolve().parent / "results"

_BATCH_FETCH_JS = """
var callback = arguments[arguments.length - 1];
var urls = Array.from(arguments).slice(0, arguments.length - 1);
var results = {};
var i = 0;
var BATCH = arguments.__chunk_size__;
var TIMEOUT = arguments.__timeout_ms__;

function next() {
    if (i >= urls.length) { callback(results); return; }
    var chunk = urls.slice(i, i + BATCH);
    i += BATCH;
    var promises = chunk.map(function(url) {
        var ctrl = new AbortController();
        var tid = setTimeout(function() { ctrl.abort(); }, TIMEOUT);
        return fetch(url, {
            credentials: 'include',
            headers: { 'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8' },
            signal: ctrl.signal
        })
        .then(function(r) { clearTimeout(tid); return r.ok ? r.text() : ''; })
        .catch(function() { clearTimeout(tid); return ''; })
        .then(function(html) { results[url] = html || ''; });
    });
    Promise.all(promises).then(next);
}
next();
"""


@dataclass
class FetchOutcome:
    url: str
    html_len: int
    elapsed_ms: float
    challenge: bool
    empty: bool


@dataclass
class ModeReport:
    mode: str
    chunk_size: int | None
    total_wall_ms: float
    outcomes: list[FetchOutcome] = field(default_factory=list)

    @property
    def n(self) -> int:
        return len(self.outcomes)

    @property
    def challenge_count(self) -> int:
        return sum(1 for o in self.outcomes if o.challenge)

    @property
    def empty_count(self) -> int:
        return sum(1 for o in self.outcomes if o.empty)

    @property
    def success_count(self) -> int:
        return self.n - self.challenge_count - self.empty_count

    def summary(self) -> dict:
        return {
            "mode": self.mode,
            "chunk_size": self.chunk_size,
            "n_urls": self.n,
            "total_wall_ms": round(self.total_wall_ms, 1),
            "avg_ms_per_url": round(self.total_wall_ms / self.n, 1) if self.n else None,
            "success": self.success_count,
            "challenge": self.challenge_count,
            "empty": self.empty_count,
            "success_rate": round(self.success_count / self.n, 3) if self.n else None,
            "challenge_rate": round(self.challenge_count / self.n, 3) if self.n else None,
        }


def load_sample_urls(db_path: Path, limit: int) -> list[str]:
    """Pega URLs reais de group-detail (Nível C) já capturadas com sucesso
    (não-captcha) no banco de produção, para testar contra o site real com
    alvos conhecidos-bons — nunca inventa URL."""
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute(
            """
            SELECT DISTINCT source_url FROM raw_capture
            WHERE source_url LIKE '%/genuine-catalogs/epc/%'
              AND source_url NOT LIKE '%captcha%'
            ORDER BY source_url
            LIMIT ?
            """,
            (limit * 6,),
        )
        rows = [r[0] for r in cur.fetchall()]
    finally:
        conn.close()
    # Formato fixo: epc/<manufacturer-overall>/<vehicle_model>/<market>/<spec_key>/<category>/<group_id>
    # -> exatamente 6 segmentos = group-detail (Nível C); menos que isso é market-index/spec-nav.
    detail_urls = [u for u in rows if len(u.rsplit("epc/", 1)[-1].split("/")) == 6]
    if len(detail_urls) < limit:
        raise SystemExit(
            f"Só encontrei {len(detail_urls)} URLs de group-detail não-captcha em "
            f"{db_path} (pedi {limit}). Rode o scraper real um pouco mais antes, "
            "ou passe --limit menor."
        )
    return detail_urls[:limit]


def attach_driver(host: str, port: int) -> webdriver.Chrome:
    options = Options()
    options.add_experimental_option("debuggerAddress", f"{host}:{port}")
    return webdriver.Chrome(options=options)


def run_navigate_baseline(driver: webdriver.Chrome, urls: list[str]) -> ModeReport:
    """Replica o modelo real: 1 navigate() sequencial por URL, na mesma aba."""
    outcomes: list[FetchOutcome] = []
    t0 = time.perf_counter()
    for url in urls:
        t_start = time.perf_counter()
        driver.get(url)
        html = driver.page_source
        elapsed_ms = (time.perf_counter() - t_start) * 1000
        result = detect_challenge(html)
        outcomes.append(
            FetchOutcome(
                url=url,
                html_len=len(html),
                elapsed_ms=elapsed_ms,
                challenge=result.detected,
                empty=len(html) < 200,
            )
        )
        print(f"  [navigate] {elapsed_ms:8.0f}ms  challenge={result.detected!s:5}  {url}")
    total_ms = (time.perf_counter() - t0) * 1000
    return ModeReport(mode="navigate", chunk_size=None, total_wall_ms=total_ms, outcomes=outcomes)


def run_batch_fetch(
    driver: webdriver.Chrome,
    urls: list[str],
    chunk_size: int,
    timeout_ms: int,
    max_urls_per_call: int = 150,
) -> ModeReport:
    """Técnica de main.py: fetch() batelado dentro do próprio Chrome via
    execute_async_script, na mesma aba/sessão já autenticada.

    Faz várias chamadas de execute_async_script (uma a cada
    `max_urls_per_call` URLs) em vez de uma única call gigante — o cliente
    HTTP do Selenium (urllib3) tem timeout próprio (~120s) que estoura antes
    do script_timeout do Chrome em lotes muito grandes; várias calls menores
    também é mais parecido com como um pipeline real operaria (main.py usa
    MAX_FETCH/batch_window pelo mesmo motivo)."""
    js = _BATCH_FETCH_JS.replace(
        "arguments.__chunk_size__", str(chunk_size)
    ).replace("arguments.__timeout_ms__", str(timeout_ms))
    n_chunks_per_call = -(-max_urls_per_call // chunk_size)
    script_timeout_s = n_chunks_per_call * (timeout_ms / 1000.0) + 60
    driver.set_script_timeout(script_timeout_s)

    html_map: dict[str, str] = {}
    n_calls = -(-len(urls) // max_urls_per_call) if urls else 0
    t0 = time.perf_counter()
    for call_i in range(n_calls):
        sub = urls[call_i * max_urls_per_call : (call_i + 1) * max_urls_per_call]
        t_sub = time.perf_counter()
        sub_map = driver.execute_async_script(js, *sub)
        html_map.update(sub_map)
        print(
            f"  (call {call_i + 1}/{n_calls}: {len(sub)} urls em "
            f"{(time.perf_counter() - t_sub) * 1000:.0f}ms)"
        )
    total_ms = (time.perf_counter() - t0) * 1000

    outcomes: list[FetchOutcome] = []
    per_url_ms = total_ms / len(urls) if urls else 0.0
    for url in urls:
        html = html_map.get(url, "") or ""
        result = detect_challenge(html) if html else None
        outcomes.append(
            FetchOutcome(
                url=url,
                html_len=len(html),
                elapsed_ms=per_url_ms,  # batelado: só temos o total, não por-URL
                challenge=bool(result and result.detected),
                empty=len(html) < 200,
            )
        )
        status = "empty" if len(html) < 200 else ("challenge" if result and result.detected else "ok")
        print(f"  [batch]    {status:9}  len={len(html):6}  {url}")
    return ModeReport(mode="batch", chunk_size=chunk_size, total_wall_ms=total_ms, outcomes=outcomes)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=None, help="default: AMAYAMA_CDP_HOST env ou 127.0.0.1")
    parser.add_argument("--port", type=int, default=None, help="default: AMAYAMA_CDP_PORT env ou 9222")
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH))
    parser.add_argument(
        "--urls-file",
        default=None,
        help="JSON com lista de URLs a testar, no lugar de amostrar do --db-path "
        "(ex.: spikes/results/golf_group_urls.json)",
    )
    parser.add_argument("--limit", type=int, default=24, help="quantas URLs testar por modo")
    parser.add_argument("--chunk-size", type=int, default=3, help="URLs por Promise.all no modo batch")
    parser.add_argument("--timeout-ms", type=int, default=30000)
    parser.add_argument(
        "--mode", choices=["navigate", "batch", "both"], default="both",
    )
    args = parser.parse_args()

    host = resolve_cdp_host(args.host)
    port = resolve_cdp_port(args.port)

    if args.urls_file:
        all_urls = json.loads(Path(args.urls_file).read_text(encoding="utf-8"))
        urls = all_urls[: args.limit]
        print(f"Amostra: {len(urls)} URLs de {args.urls_file} (de {len(all_urls)} disponíveis)\n")
    else:
        urls = load_sample_urls(Path(args.db_path), args.limit)
        print(f"Amostra: {len(urls)} URLs reais de group-detail (raw_capture, não-captcha)\n")

    print(f"Conectando via CDP em {host}:{port} (Chrome já aberto, sessão do operador)...")
    driver = attach_driver(host, port)

    reports: list[ModeReport] = []
    try:
        if args.mode in ("navigate", "both"):
            print("\n=== MODO NAVIGATE (baseline atual: driver.get() sequencial) ===")
            reports.append(run_navigate_baseline(driver, urls))
        if args.mode in ("batch", "both"):
            print(f"\n=== MODO BATCH (fetch() no navegador, chunk={args.chunk_size}) ===")
            reports.append(run_batch_fetch(driver, urls, args.chunk_size, args.timeout_ms))
    finally:
        pass  # nunca fecha o Chrome do operador

    print("\n" + "=" * 70)
    print("RESUMO")
    print("=" * 70)
    summaries = []
    for r in reports:
        s = r.summary()
        summaries.append(s)
        print(json.dumps(s, indent=2, ensure_ascii=False))

    if len(reports) == 2:
        nav, batch = reports[0], reports[1]
        speedup = nav.total_wall_ms / batch.total_wall_ms if batch.total_wall_ms else float("inf")
        print(f"\nSpeedup batch vs navigate: {speedup:.2f}x")
        print(
            f"Challenge rate: navigate={nav.challenge_count}/{nav.n} "
            f"vs batch={batch.challenge_count}/{batch.n}"
        )

    RESULTS_DIR.mkdir(exist_ok=True)
    out_path = RESULTS_DIR / f"spike_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    out_path.write_text(json.dumps(summaries, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nResultado salvo em {out_path}")


if __name__ == "__main__":
    main()
