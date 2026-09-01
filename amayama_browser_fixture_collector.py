#!/usr/bin/env python3
"""
Amayama browser-assisted fixture collector v3.

Temporary acquisition helper only.
- Attaches to an already-open Chrome via remote debugging.
- Visits a fixed allow-list of real Amayama group-detail URLs sequentially.
- Detects CAPTCHA / Cloudflare from VISIBLE browser state.
- Pauses for manual resolution; never solves or bypasses a challenge.
- Validates the real EPC DOM before saving.
- Does not close the user's Chrome.

This helper must not be added to the production scraper feature.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

BASE = (
    "https://www.amayama.com/en/genuine-catalogs/epc/"
    "volkswagen-overall/amarok/ama-br"
)

TARGETS = [
    ("2hbc3x-56060", "body", "800"),
    ("s1bc3x-56087", "body", "800"),
    ("s6bc74-61127", "engine", "100"),
    ("s7bc74-61187", "engine", "100"),
    ("s6bc74-61127", "front-axle-steering", "407"),
    ("s7bc74-61187", "front-axle-steering", "407"),
    ("s6bc74-61127", "body", "800"),
    ("s7bc74-61187", "body", "800"),
    ("s7bc8a-62184", "engine", "100"),
    ("agdc8a-62169", "engine", "100"),
    ("s7bc8a-62184", "front-axle-steering", "407"),
    ("agdc8a-62169", "front-axle-steering", "407"),
    ("s7bc8a-62184", "body", "800"),
    ("agdc8a-62169", "body", "800"),
]

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
    '#challenge-error-text',
    '.cf-turnstile',
)

SUCCESS_SELECTORS = (
    ".epcFullPage",
    ".epcSchema",
    ".epcSchema__schemas",
)

DETAIL_SELECTORS = (
    ".epcSchema__schema[data-id]",
    ".entriesTable",
)


def build_url(spec: str, category: str, group_id: str) -> str:
    return f"{BASE}/{spec}/{category}/{group_id}"


def output_name(spec: str, category: str, group_id: str) -> str:
    return f"{spec}__{category.replace('/', '_')}__{group_id}.html"


def normalized_url(url: str) -> str:
    parts = urlsplit(url)
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, "", ""))


def visible_body_text(driver: webdriver.Chrome) -> str:
    try:
        return driver.find_element(By.TAG_NAME, "body").text or ""
    except Exception:
        return ""


def challenge_present(driver: webdriver.Chrome) -> bool:
    text = visible_body_text(driver).lower()
    title = (driver.title or "").lower()

    try:
        current = urlsplit(driver.current_url)
        if current.path.rstrip("/").lower().endswith("/captcha.html"):
            return True
    except Exception:
        pass

    if any(marker in text for marker in VISIBLE_BLOCK_MARKERS):
        return True

    if "just a moment" in title or "um momento" in title:
        return True

    for selector in CHALLENGE_SELECTORS:
        try:
            if driver.find_elements(By.CSS_SELECTOR, selector):
                return True
        except Exception:
            pass

    return False


def expected_identity_loaded(driver: webdriver.Chrome, expected_url: str) -> bool:
    try:
        if normalized_url(driver.current_url) != normalized_url(expected_url):
            return False
    except Exception:
        return False

    for selector in SUCCESS_SELECTORS:
        try:
            if not driver.find_elements(By.CSS_SELECTOR, selector):
                return False
        except Exception:
            return False

    # Require real schema/parts content, but allow either representation.
    has_detail = False
    for selector in DETAIL_SELECTORS:
        try:
            if driver.find_elements(By.CSS_SELECTOR, selector):
                has_detail = True
                break
        except Exception:
            pass

    return has_detail


def wait_for_page(
    driver: webdriver.Chrome,
    expected_url: str,
    *,
    timeout: float,
) -> bool:
    deadline = time.monotonic() + timeout
    prompted = False
    last_status = 0.0

    while time.monotonic() < deadline:
        if expected_identity_loaded(driver, expected_url):
            return True

        if challenge_present(driver):
            if not prompted:
                print("\nCAPTCHA / Cloudflare detectado.")
                print(f"URL atual: {driver.current_url}")
                print("Resolva manualmente na janela do Chrome.")
                input(
                    "Só pressione ENTER depois que o CAPTCHA terminar "
                    "e a página REAL da Amayama aparecer... "
                )
                prompted = True
                # Never navigate/reload here. Keep the human-cleared session intact.
                time.sleep(1.0)
                continue

            # After the human confirms, just observe the existing tab.
            now = time.monotonic()
            if now - last_status >= 10.0:
                print(
                    "Aguardando a página sair do CAPTCHA... "
                    f"url={driver.current_url}"
                )
                last_status = now
            time.sleep(0.5)
            continue

        # Challenge disappeared. The site may take a moment to render the EPC.
        time.sleep(0.5)

    return expected_identity_loaded(driver, expected_url)


def save_diagnostics(
    driver: webdriver.Chrome,
    out_dir: Path,
    idx: int,
) -> None:
    html = driver.page_source or ""
    body = visible_body_text(driver)

    (out_dir / f"_unexpected_{idx:02d}.html").write_text(
        html, encoding="utf-8"
    )
    (out_dir / f"_unexpected_{idx:02d}.txt").write_text(
        body, encoding="utf-8"
    )

    try:
        driver.save_screenshot(str(out_dir / f"_unexpected_{idx:02d}.png"))
    except Exception:
        pass

    print(f"title: {driver.title!r}")
    print(f"url:   {driver.current_url}")
    print(f"challenge_detected: {challenge_present(driver)}")
    print(
        "DOM counts: "
        f"epcFullPage={len(driver.find_elements(By.CSS_SELECTOR, '.epcFullPage'))}, "
        f"epcSchema={len(driver.find_elements(By.CSS_SELECTOR, '.epcSchema'))}, "
        f"schemas={len(driver.find_elements(By.CSS_SELECTOR, '.epcSchema__schema[data-id]'))}, "
        f"entriesTable={len(driver.find_elements(By.CSS_SELECTOR, '.entriesTable'))}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--debugger-address", required=True)
    parser.add_argument("--driver", required=True)
    parser.add_argument("--out", default="amayama-fixtures")
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--delay", type=float, default=2.0)
    parser.add_argument("--timeout", type=float, default=300.0)
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    options = Options()
    options.add_experimental_option("debuggerAddress", args.debugger_address)

    try:
        driver = webdriver.Chrome(
            service=Service(args.driver),
            options=options,
        )
    except WebDriverException as exc:
        print("Não foi possível conectar ao Chrome.")
        print(f"debugger-address: {args.debugger_address}")
        print(f"driver: {args.driver}")
        print(f"erro: {exc}")
        return 2

    total = len(TARGETS)

    try:
        for idx, (spec, category, group_id) in enumerate(TARGETS, start=1):
            if idx < args.start:
                continue

            url = build_url(spec, category, group_id)
            target = out_dir / output_name(spec, category, group_id)

            if target.exists() and target.stat().st_size > 0:
                print(f"[{idx}/{total}] SKIP: {target}")
                continue

            print(f"\n[{idx}/{total}] {url}")

            try:
                driver.get(url)
            except WebDriverException as exc:
                print(f"Falha de navegação: {exc}")
                print(f"Retome depois com --start {idx}")
                return 3

            if not wait_for_page(driver, url, timeout=args.timeout):
                print("\nSTOP: página não passou na validação estrutural.")
                save_diagnostics(driver, out_dir, idx)
                print(f"Diagnóstico salvo em {out_dir}/_unexpected_{idx:02d}.*")
                print(f"Retome depois com --start {idx}")
                return 4

            html = driver.page_source or ""
            target.write_text(html, encoding="utf-8")

            schemas = len(
                driver.find_elements(
                    By.CSS_SELECTOR, ".epcSchema__schema[data-id]"
                )
            )
            tables = len(
                driver.find_elements(By.CSS_SELECTOR, ".entriesTable")
            )

            print(
                f"OK: {target} "
                f"({len(html):,} chars, schemas={schemas}, tables={tables})"
            )

            if idx != total:
                time.sleep(args.delay)

        print("\nDONE: todas as páginas foram capturadas.")
        return 0

    finally:
        # Keep the user's existing Chrome open.
        try:
            driver.service.stop()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
