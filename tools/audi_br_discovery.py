"""Discovery-only dos scopes Audi Brasil via Chrome CDP visível.

Não visita SPEC_NAVIGATION nem grupos: lê o ItemList JSON-LD da marca para
modelos, o ItemList de cada modelo para mercados BR e o índice de cada
mercado para contar as specs. Em CAPTCHA, apenas espera resolução manual.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from amayama_scraper.parsing.market_index import parse_market_spec_index
from amayama_scraper.transport.chrome_cdp_adapter import ChromeCdpTransport
from amayama_scraper.validation.detectors.challenge import detect_challenge

BASE_URL = "https://www.amayama.com/en/genuine-catalogs/audi"
OUTPUT_JSON = Path("audi_br_final_discovery.json")
OUTPUT_CSV = Path("audi_br_final_scopes.csv")
POLL_SECONDS = 5.0
MIN_INTERVAL_SECONDS = 1.0


def _item_list(html: str) -> list[dict[str, object]]:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(tag.string or tag.get_text())
        except json.JSONDecodeError:
            continue
        for candidate in data if isinstance(data, list) else [data]:
            if isinstance(candidate, dict) and candidate.get("@type") == "ItemList":
                items = candidate.get("itemListElement")
                if isinstance(items, list):
                    return [item for item in items if isinstance(item, dict)]
    return []


def _is_brazil_market(url: str) -> bool:
    parts = [part.lower() for part in urlparse(url).path.rstrip("/").split("/")]
    return len(parts) >= 2 and parts[-2:-1] != [] and parts[-1].endswith("-br")


def _write_report(scopes: list[dict[str, object]], pending: list[dict[str, str]]) -> None:
    scopes.sort(key=lambda row: (int(row["specs"]), str(row["vehicle_model"]), str(row["market"])))
    payload = {
        "manufacturer": "AUDI",
        "source": BASE_URL,
        "scopes": scopes,
        "pending": pending,
        "total_scopes": len(scopes),
        "total_specs": sum(int(row["specs"]) for row in scopes),
    }
    OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["vehicle_model,market,specs,market_index_url"]
    lines.extend(
        f'{row["vehicle_model"]},{row["market"]},{row["specs"]},{row["market_index_url"]}'
        for row in scopes
    )
    OUTPUT_CSV.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    transport = ChromeCdpTransport(port=9222)
    last_request = 0.0
    pending: list[dict[str, str]] = []

    def capture(url: str):
        nonlocal last_request
        delay = MIN_INTERVAL_SECONDS - (time.monotonic() - last_request)
        if delay > 0:
            time.sleep(delay)
        current = transport.navigate(url)
        last_request = time.monotonic()
        detection = detect_challenge(current.page_source, source_url=current.effective_url)
        while detection.detected:
            event = {"url": url, "effective_url": current.effective_url, "status": "CHALLENGE"}
            if not pending or pending[-1] != event:
                pending.append(event)
                _write_report(scopes, pending)
                print(f"CHALLENGE manual pendente: {current.effective_url}", flush=True)
            time.sleep(POLL_SECONDS)
            current = transport.current_capture()
            detection = detect_challenge(current.page_source, source_url=current.effective_url)
        return current

    scopes: list[dict[str, object]] = []
    brand = capture(BASE_URL)
    models = _item_list(brand.page_source)
    print(f"Modelos Audi encontrados: {len(models)}", flush=True)
    for index, model in enumerate(models, start=1):
        model_name, model_url = model.get("name"), model.get("url")
        if not isinstance(model_name, str) or not isinstance(model_url, str):
            continue
        model_page = capture(model_url)
        brazil_markets = [
            item for item in _item_list(model_page.page_source)
            if isinstance(item.get("url"), str) and _is_brazil_market(item["url"])
        ]
        for market_item in brazil_markets:
            market_url = str(market_item["url"])
            market = urlparse(market_url).path.rstrip("/").split("/")[-1].upper()
            market_page = capture(market_url)
            parsed = parse_market_spec_index(market_page.page_source, source_capture_id=market_url)
            if parsed.critical_error is not None:
                pending.append({"url": market_url, "effective_url": market_page.effective_url, "status": "PARSE_ERROR"})
                continue
            scopes.append({
                "vehicle_model": model_name,
                "market": market,
                "specs": len(parsed.entries),
                "market_index_url": market_url,
            })
            _write_report(scopes, pending)
            print(f"[{index}/{len(models)}] {model_name} | {market} | {len(parsed.entries)} specs", flush=True)
    _write_report(scopes, pending)
    print(f"FINAL scopes={len(scopes)} specs={sum(int(row['specs']) for row in scopes)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
