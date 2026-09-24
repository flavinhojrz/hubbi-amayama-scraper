"""Audita scopes Audi BR por conjuntos exatos de specs, sem coletar peças."""

from __future__ import annotations

import json
import time
from pathlib import Path

from amayama_scraper.parsing.market_index import parse_market_spec_index
from amayama_scraper.transport.chrome_cdp_adapter import ChromeCdpTransport
from amayama_scraper.validation.detectors.challenge import detect_challenge

SOURCE = Path("audi_br_final_discovery.json")
OUTPUT = Path("audi_br_scope_audit.json")


def main() -> int:
    discovery = json.loads(SOURCE.read_text(encoding="utf-8"))
    transport = ChromeCdpTransport(port=9222)
    rows: list[dict[str, object]] = []
    pending: list[str] = []
    for index, scope in enumerate(discovery["scopes"], start=1):
        url = str(scope["market_index_url"])
        capture = transport.navigate(url)
        while detect_challenge(capture.page_source, source_url=capture.effective_url).detected:
            if url not in pending:
                pending.append(url)
                print(f"CHALLENGE manual pendente: {capture.effective_url}", flush=True)
            time.sleep(5)
            capture = transport.current_capture()
        parsed = parse_market_spec_index(capture.page_source, source_capture_id=url)
        if parsed.critical_error is not None:
            raise RuntimeError(f"índice inválido: {url}: {parsed.critical_error.message}")
        specs = sorted(
            (entry.amayama_catalog_id, entry.model_code, entry.source_url)
            for entry in parsed.entries
        )
        rows.append({**scope, "spec_set": specs})
        print(f"[{index}/31] {scope['vehicle_model']} | {len(specs)} specs", flush=True)
        time.sleep(1)

    groups: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        # URL de índice é evidência do alias, mas muda com o slug do modelo.
        # A identidade canônica de uma spec é catálogo + model_code.
        fingerprint = json.dumps(
            [(catalog_id, model_code) for catalog_id, model_code, _url in row["spec_set"]],
            separators=(",", ":"),
        )
        groups.setdefault(fingerprint, []).append(row)
    unique = [members[0] for members in groups.values()]
    aliases = [
        {
            "canonical": {key: members[0][key] for key in ("vehicle_model", "market", "specs", "market_index_url")},
            "aliases": [{key: item[key] for key in ("vehicle_model", "market", "specs", "market_index_url")} for item in members[1:]],
        }
        for members in groups.values() if len(members) > 1
    ]
    unique_specs = {
        (catalog_id, model_code)
        for row in unique
        for catalog_id, model_code, _url in row["spec_set"]
    }
    report = {"original_scopes": len(rows), "unique_scopes": len(unique), "unique_specs": len(unique_specs), "aliases": aliases, "scopes": unique}
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"FINAL original={len(rows)} unique={len(unique)} unique_specs={len(unique_specs)} aliases={len(aliases)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
