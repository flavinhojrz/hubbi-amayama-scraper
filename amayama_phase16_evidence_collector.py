#!/usr/bin/env python3
"""
Temporary Phase 16 evidence collector for Amayama Amarok AMA-BR.

Purpose
-------
1) Materialize the 7 real SPEC_NAVIGATION manifests in the local workspace.
2) Re-capture valid non-challenge engine/100 pages for 2HBC3X and S1BC3X.
3) Search the real S6BC74/S7BC74 common group set and stop at the first
   group-detail pair where:
   - the parsed parts payload is equal;
   - the schema set is equal;
   - at least one matching schema has image presence on only one side.

Safety / scope
--------------
- Attaches to a Chrome session already opened by the user.
- Does not solve, bypass, or automate CAPTCHA / Cloudflare.
- If a challenge appears, pauses for manual resolution.
- Does not close the user's Chrome.
- Temporary acquisition helper only. Do not add it to src/ or production deps.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By


BASE = (
    "https://www.amayama.com/en/genuine-catalogs/epc/"
    "volkswagen-overall/amarok/ama-br"
)

MANIFEST_SPECS = (
    "2hbc3x-56060",
    "s1bc3x-56087",
    "s6bc74-61127",
    "s7bc74-61187",
    "s7bc8a-62184",
    "agdc8a-62169",
    "s7bc8a-61189",
)

ENGINE_100_TARGETS = (
    ("2hbc3x-56060", "engine", "100"),
    ("s1bc3x-56087", "engine", "100"),
)

S6_SPEC = "s6bc74-61127"
S7_SPEC = "s7bc74-61187"

ALREADY_TESTED_S6_S7 = {
    ("engine", "100"),
    ("front-axle-steering", "407"),
    ("body", "800"),
}

VISIBLE_BLOCK_MARKERS = (
    "we’ve noticed some unusual activity",
    "we've noticed some unusual activity",
    "your activity is recognized as suspicious",
    "recognized as suspicious",
    "please complete the captcha verification",
    "confirm you're not a bot",
    "confirm you are not a bot",
    "captcha is loading",
    "executando verificação de segurança",
    "executando verificacao de seguranca",
    "checking your browser",
    "performing security verification",
    "security verification",
)

CHALLENGE_SELECTORS = (
    'input[name="cf-turnstile-response"]',
    "#challenge-error-text",
    ".cf-turnstile",
)

MANIFEST_SELECTORS = (
    ".epcVariation__details",
    ".epcVariation__schemaGroups",
    ".epcVariation__schemas .epcVariation__schema[data-id]",
)

DETAIL_SELECTORS = (
    ".epcFullPage",
    ".epcSchema",
    ".epcSchema__schemas",
    ".epcSchema__schema[data-id]",
    ".entriesTable",
)


@dataclass(frozen=True)
class GroupRef:
    category: str
    group_id: str
    thumbnail_key: str | None = None


@dataclass(frozen=True)
class GroupEvidence:
    spec: str
    category: str
    group_id: str
    source_url: str
    schema_ids: tuple[str, ...]
    image_presence: dict[str, bool]
    parts_signature: str
    html: str


def build_manifest_url(spec: str) -> str:
    return f"{BASE}/{spec}"


def build_group_url(spec: str, category: str, group_id: str) -> str:
    return f"{BASE}/{spec}/{category}/{group_id}"


def normalize_url(url: str) -> str:
    parts = urlsplit(url)
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, "", ""))


def norm_text(value: str) -> str:
    return " ".join(value.split())


def looks_like_challenge_url(url: str) -> bool:
    parts = urlsplit(url)
    return parts.path.rstrip("/").lower().endswith("/captcha.html")


def visible_text(driver: webdriver.Chrome) -> str:
    try:
        return driver.find_element(By.TAG_NAME, "body").text or ""
    except Exception:
        return ""


def challenge_present(driver: webdriver.Chrome) -> bool:
    if looks_like_challenge_url(driver.current_url or ""):
        return True

    title = (driver.title or "").lower()
    if "just a moment" in title or "um momento" in title:
        return True

    text = visible_text(driver).lower()
    if any(marker in text for marker in VISIBLE_BLOCK_MARKERS):
        return True

    for selector in CHALLENGE_SELECTORS:
        try:
            if driver.find_elements(By.CSS_SELECTOR, selector):
                return True
        except Exception:
            pass

    return False


def has_selectors(driver: webdriver.Chrome, selectors: tuple[str, ...]) -> bool:
    try:
        return all(driver.find_elements(By.CSS_SELECTOR, selector) for selector in selectors)
    except Exception:
        return False


def page_matches_expected(driver: webdriver.Chrome, expected_url: str) -> bool:
    return normalize_url(driver.current_url or "") == normalize_url(expected_url)


def page_ready(
    driver: webdriver.Chrome,
    expected_url: str,
    selectors: tuple[str, ...],
) -> bool:
    if challenge_present(driver):
        return False
    return page_matches_expected(driver, expected_url) and has_selectors(driver, selectors)


def wait_for_real_page(
    driver: webdriver.Chrome,
    expected_url: str,
    selectors: tuple[str, ...],
    timeout: int,
) -> None:
    deadline = time.time() + timeout
    prompted = False

    while time.time() < deadline:
        if page_ready(driver, expected_url, selectors):
            return

        if challenge_present(driver):
            if not prompted:
                print()
                print("=" * 78)
                print("CAPTCHA / Cloudflare detectado.")
                print("Resolva MANUALMENTE no Chrome aberto.")
                print("O script não tentará resolver ou contornar o desafio.")
                print(f"Destino esperado: {expected_url}")
                print("=" * 78)
                input("Depois que a página real carregar no Chrome, pressione ENTER...")
                prompted = True
            else:
                time.sleep(0.8)
            continue

        time.sleep(0.5)

    raise RuntimeError(
        "Timeout esperando a página real do catálogo.\n"
        f"Esperado: {expected_url}\n"
        f"Atual:    {driver.current_url}\n"
        f"Título:   {driver.title}"
    )


def navigate_real(
    driver: webdriver.Chrome,
    url: str,
    selectors: tuple[str, ...],
    timeout: int,
) -> str:
    print(f"\nAbrindo: {url}")
    driver.get(url)
    wait_for_real_page(driver, url, selectors, timeout)
    html = driver.page_source or ""
    if not html.strip():
        raise RuntimeError(f"HTML vazio após validação: {url}")
    return html


def save_html(path: Path, html: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")


def extract_manifest_groups(html: str, spec: str) -> list[GroupRef]:
    soup = BeautifulSoup(html, "html.parser")
    spec_lower = spec.lower()
    prefix = f"/{spec_lower}/"

    groups: list[GroupRef] = []
    seen: set[tuple[str, str]] = set()

    for card in soup.select(".epcVariation__schema[data-id]"):
        anchor = card.select_one(".epcVariation__schema-name a[href]")
        if anchor is None:
            anchor = card.select_one("a[href]")
        if anchor is None:
            continue

        href = str(anchor.get("href") or "")
        path = urlsplit(href).path.lower()
        marker = path.find(prefix)
        if marker < 0:
            continue

        tail = path[marker + len(prefix):].strip("/").split("/")
        if len(tail) != 2:
            continue

        category, group_id = tail
        if not group_id.isdigit():
            continue

        key = (category, group_id)
        if key in seen:
            continue
        seen.add(key)

        img = card.select_one(".epcVariation__schema-photo img[src]")
        thumb = None
        if img is not None:
            src = str(img.get("src") or "").strip()
            if src:
                thumb = Path(urlsplit(src).path).name.lower() or None

        groups.append(GroupRef(category=category, group_id=group_id, thumbnail_key=thumb))

    if not groups:
        raise RuntimeError(f"Nenhum group link extraído do manifesto {spec}")

    return groups


def _clean_image_src(src: str | None) -> str | None:
    if not src:
        return None
    value = src.strip()
    if not value:
        return None
    if "image_not_found" in value.lower():
        return None
    return value


def extract_group_evidence(
    html: str,
    spec: str,
    category: str,
    group_id: str,
    source_url: str,
) -> GroupEvidence:
    soup = BeautifulSoup(html, "html.parser")
    schemas = soup.select(".epcSchema__schema[data-id]")
    if not schemas:
        raise RuntimeError(f"Sem schemas reais em {source_url}")

    schema_ids: list[str] = []
    image_presence: dict[str, bool] = {}
    semantic_rows: list[tuple[str, tuple[tuple[str, ...], ...]]] = []

    for schema in schemas:
        schema_id = str(schema.get("data-id") or "").strip()
        if not schema_id:
            raise RuntimeError(f"Schema sem data-id em {source_url}")
        schema_ids.append(schema_id)

        img = schema.select_one(".imgMap img[src]")
        img_src = _clean_image_src(str(img.get("src")) if img is not None else None)

        if img_src is None:
            img_map = schema.select_one(".imgMap[style]")
            style = str(img_map.get("style") or "") if img_map is not None else ""
            match = re.search(r"url\([\"']?([^\"')]+)", style, flags=re.IGNORECASE)
            if match:
                img_src = _clean_image_src(match.group(1))

        image_presence[schema_id] = img_src is not None

        rows: list[tuple[str, ...]] = []
        for tr in schema.select(".entriesTable tr[data-key]"):
            data_key = norm_text(str(tr.get("data-key") or ""))

            values: list[str] = [data_key]
            for selector in (
                ".entriesPncTable__groupHeader",
                ".entriesTable__number",
                ".entriesTable__description",
                ".entriesPncDescriptionTable",
                ".entriesTable__period",
                ".entriesTable__required",
            ):
                selected = tr.select(selector)
                values.append(
                    " || ".join(norm_text(node.get_text(" ", strip=True)) for node in selected)
                )

            rows.append(tuple(values))

        semantic_rows.append((schema_id, tuple(rows)))

    payload = repr(tuple(semantic_rows)).encode("utf-8")
    signature = hashlib.sha256(payload).hexdigest()

    return GroupEvidence(
        spec=spec,
        category=category,
        group_id=group_id,
        source_url=source_url,
        schema_ids=tuple(schema_ids),
        image_presence=image_presence,
        parts_signature=signature,
        html=html,
    )


def same_parts(a: GroupEvidence, b: GroupEvidence) -> bool:
    return a.schema_ids == b.schema_ids and a.parts_signature == b.parts_signature


def image_presence_diff(a: GroupEvidence, b: GroupEvidence) -> list[str]:
    if a.schema_ids != b.schema_ids:
        return []
    return [
        schema_id
        for schema_id in a.schema_ids
        if a.image_presence.get(schema_id) != b.image_presence.get(schema_id)
    ]


def build_common_candidates(
    s6_groups: list[GroupRef],
    s7_groups: list[GroupRef],
) -> list[GroupRef]:
    s7_map = {(g.category, g.group_id): g for g in s7_groups}
    common: list[GroupRef] = []

    for s6 in s6_groups:
        key = (s6.category, s6.group_id)
        s7 = s7_map.get(key)
        if s7 is None or key in ALREADY_TESTED_S6_S7:
            continue

        # Prioritize groups whose manifest thumbnail evidence is already asymmetric.
        priority_thumb = None
        if (s6.thumbnail_key is None) != (s7.thumbnail_key is None):
            priority_thumb = "__presence_diff__"
        elif s6.thumbnail_key and s7.thumbnail_key and s6.thumbnail_key != s7.thumbnail_key:
            priority_thumb = "__url_diff__"
        else:
            priority_thumb = s6.thumbnail_key

        common.append(
            GroupRef(
                category=s6.category,
                group_id=s6.group_id,
                thumbnail_key=priority_thumb,
            )
        )

    def priority(group: GroupRef) -> tuple[int, int]:
        asymmetric = group.thumbnail_key in {"__presence_diff__", "__url_diff__"}
        # Keep source order otherwise. list.index is avoided by enumerate below.
        return (0 if asymmetric else 1, 0)

    enumerated = list(enumerate(common))
    enumerated.sort(
        key=lambda item: (
            0 if item[1].thumbnail_key in {"__presence_diff__", "__url_diff__"} else 1,
            item[0],
        )
    )
    return [group for _, group in enumerated]


def capture_manifests(
    driver: webdriver.Chrome,
    out: Path,
    timeout: int,
) -> dict[str, str]:
    html_by_spec: dict[str, str] = {}

    print("\n" + "=" * 78)
    print("ETAPA A — 7 manifests SPEC_NAVIGATION")
    print("=" * 78)

    for index, spec in enumerate(MANIFEST_SPECS, start=1):
        url = build_manifest_url(spec)
        print(f"[manifest {index}/{len(MANIFEST_SPECS)}] {spec}")
        html = navigate_real(driver, url, MANIFEST_SELECTORS, timeout)

        # Validate that links for this exact spec exist.
        groups = extract_manifest_groups(html, spec)
        print(f"  OK: {len(groups)} grupos encontrados")

        path = out / "manifests" / f"{spec}__manifest.html"
        save_html(path, html)
        html_by_spec[spec] = html
        print(f"  salvo: {path}")

    return html_by_spec


def capture_engine_pair(
    driver: webdriver.Chrome,
    out: Path,
    timeout: int,
) -> None:
    print("\n" + "=" * 78)
    print("ETAPA B — 2HBC3X ↔ S1BC3X / engine/100 válidos")
    print("=" * 78)

    evidence: list[GroupEvidence] = []

    for spec, category, group_id in ENGINE_100_TARGETS:
        url = build_group_url(spec, category, group_id)
        html = navigate_real(driver, url, DETAIL_SELECTORS, timeout)
        ev = extract_group_evidence(html, spec, category, group_id, url)
        evidence.append(ev)

        path = out / "groups" / f"{spec}__{category}__{group_id}.html"
        save_html(path, html)
        print(
            f"  OK: schemas={len(ev.schema_ids)} "
            f"parts_signature={ev.parts_signature[:12]}…"
        )
        print(f"  salvo: {path}")

    a, b = evidence
    print()
    if same_parts(a, b):
        print("Diagnóstico local: parts payload idêntico no engine/100.")
    else:
        print(
            "ATENÇÃO: engine/100 capturado com diferença semântica entre as specs.\n"
            "Os arquivos foram preservados, mas o script não afirmará equivalência."
        )


def search_s6_s7_image_asymmetry(
    driver: webdriver.Chrome,
    out: Path,
    manifests: dict[str, str],
    timeout: int,
    delay: float,
    max_candidates: int,
) -> dict[str, object] | None:
    print("\n" + "=" * 78)
    print("ETAPA C — procurar 1 grupo S6BC74/S7BC74 com assimetria real de imagem")
    print("=" * 78)

    s6_groups = extract_manifest_groups(manifests[S6_SPEC], S6_SPEC)
    s7_groups = extract_manifest_groups(manifests[S7_SPEC], S7_SPEC)
    candidates = build_common_candidates(s6_groups, s7_groups)

    if max_candidates > 0:
        candidates = candidates[:max_candidates]

    print(
        f"Grupos comuns candidatos: {len(candidates)} "
        f"(excluídos 100, 407 e 800 já testados)"
    )

    for idx, group in enumerate(candidates, start=1):
        print()
        print(
            f"[candidato {idx}/{len(candidates)}] "
            f"{group.category}/{group.group_id}"
        )

        pair: list[GroupEvidence] = []

        for spec in (S6_SPEC, S7_SPEC):
            url = build_group_url(spec, group.category, group.group_id)
            html = navigate_real(driver, url, DETAIL_SELECTORS, timeout)
            ev = extract_group_evidence(
                html,
                spec,
                group.category,
                group.group_id,
                url,
            )
            pair.append(ev)
            time.sleep(delay)

        s6_ev, s7_ev = pair

        if s6_ev.schema_ids != s7_ev.schema_ids:
            print("  rejeitado: schema IDs diferem")
            continue

        if s6_ev.parts_signature != s7_ev.parts_signature:
            print("  rejeitado: payload de peças difere")
            continue

        diff_schema_ids = image_presence_diff(s6_ev, s7_ev)
        if not diff_schema_ids:
            print("  parts iguais, mas sem assimetria de presença de imagem")
            continue

        candidate_dir = (
            out
            / "s6-s7-image-asymmetry"
            / f"{group.category}__{group.group_id}"
        )
        s6_path = candidate_dir / f"{S6_SPEC}__{group.category}__{group.group_id}.html"
        s7_path = candidate_dir / f"{S7_SPEC}__{group.category}__{group.group_id}.html"
        save_html(s6_path, s6_ev.html)
        save_html(s7_path, s7_ev.html)

        report = {
            "status": "FOUND",
            "category": group.category,
            "group_id": group.group_id,
            "s6_spec": S6_SPEC,
            "s7_spec": S7_SPEC,
            "schema_ids": list(s6_ev.schema_ids),
            "parts_signature": s6_ev.parts_signature,
            "parts_equal": True,
            "image_presence_diff_schema_ids": diff_schema_ids,
            "s6_image_presence": s6_ev.image_presence,
            "s7_image_presence": s7_ev.image_presence,
            "s6_url": s6_ev.source_url,
            "s7_url": s7_ev.source_url,
            "s6_file": str(s6_path),
            "s7_file": str(s7_path),
        }
        report_path = candidate_dir / "report.json"
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        print()
        print("*** EVIDÊNCIA ENCONTRADA ***")
        print(f"grupo: {group.category}/{group.group_id}")
        print("parts payload: IGUAL")
        print(f"schemas com presença de imagem diferente: {', '.join(diff_schema_ids)}")
        print(f"S6: {s6_path}")
        print(f"S7: {s7_path}")
        print(f"relatório: {report_path}")
        return report

    print()
    print(
        "Nenhum candidato satisfatório foi encontrado dentro do limite atual.\n"
        "Nada foi forçado. Rode novamente com --max-candidates 0 para testar "
        "todos os grupos comuns, ou aumente o limite."
    )
    return None


def attach_chrome(debugger_address: str, driver_path: str | None) -> webdriver.Chrome:
    options = Options()
    options.add_experimental_option("debuggerAddress", debugger_address)

    if driver_path:
        service = Service(executable_path=driver_path)
        return webdriver.Chrome(service=service, options=options)

    return webdriver.Chrome(options=options)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--debugger-address",
        required=True,
        help="Chrome remote debugging address, e.g. 172.25.192.1:9223",
    )
    parser.add_argument(
        "--driver",
        default=None,
        help="Path to a ChromeDriver compatible with the already-open Chrome.",
    )
    parser.add_argument(
        "--out",
        default="amayama-phase16-evidence",
        help="Output directory.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=180,
        help="Seconds to wait for each real page / manual challenge resolution.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Polite delay between S6/S7 candidate page loads.",
    )
    parser.add_argument(
        "--max-candidates",
        type=int,
        default=24,
        help="Maximum S6/S7 group pairs to inspect; 0 means all common groups.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)

    print("Amayama Phase 16 evidence collector")
    print(f"Chrome: {args.debugger_address}")
    print(f"Output: {out}")
    print("CAPTCHA/Cloudflare: somente resolução manual pelo usuário.")

    driver: webdriver.Chrome | None = None
    try:
        driver = attach_chrome(args.debugger_address, args.driver)

        manifests = capture_manifests(driver, out, args.timeout)
        capture_engine_pair(driver, out, args.timeout)
        result = search_s6_s7_image_asymmetry(
            driver,
            out,
            manifests,
            args.timeout,
            args.delay,
            args.max_candidates,
        )

        summary = {
            "manifests_captured": list(MANIFEST_SPECS),
            "engine_100_captured": [
                {
                    "spec": spec,
                    "category": category,
                    "group_id": group_id,
                }
                for spec, category, group_id in ENGINE_100_TARGETS
            ],
            "s6_s7_image_asymmetry": result,
        }
        summary_path = out / "summary.json"
        summary_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        print()
        print("=" * 78)
        print("COLETA CONCLUÍDA")
        print(f"Resumo: {summary_path}")
        if result is None:
            print("Phase 16 continua sem evidência de imagem suficiente para T246.")
            return 2

        print("Material mínimo de aquisição para retomar T245–T247/T249 foi produzido.")
        return 0

    except KeyboardInterrupt:
        print("\nInterrompido pelo usuário. Arquivos já salvos permanecem preservados.")
        return 130
    except WebDriverException as exc:
        print(f"\nErro WebDriver/Chrome: {exc}", file=sys.stderr)
        return 3
    except Exception as exc:
        print(f"\nErro: {exc}", file=sys.stderr)
        return 1
    finally:
        # Important: attached Chrome belongs to the user.
        # We intentionally do not call driver.quit().
        pass


if __name__ == "__main__":
    raise SystemExit(main())
