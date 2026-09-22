"""T011/T012 (002) — Selenium/CDP é permitido, mas SOMENTE nos adapters de
transporte (`transport/chrome_cdp_adapter.py`, `transport/
undetected_chrome_adapter.py`) — research.md §13 de 002, DEC-007.

Histórico: T239 (001) afirmava que NENHUM arquivo de `src/` importava
Selenium/Playwright/CDP — correto sob DEC-001 de 001. A feature
`002-amarok-ama-br-browser-scraper` introduziu o transporte real por Chrome,
isolado em um único arquivo (`chrome_cdp_adapter.py`, anexa a um Chrome já
aberto, nunca resolve challenge). A invariante original (nenhuma lógica de
domínio/parsing/validação/persistência/orquestração genérica toca Selenium)
continua 100% verificada abaixo.

2026-09-10 — decisão explícita do usuário (substitui DEC-007/Constitution §5
só para o transporte novo, não para o resto do projeto): `undetected_
chromedriver` deixa de ser proibido — `transport/undetected_chrome_adapter.py`
é um SEGUNDO arquivo permitido, que lança seu próprio Chrome e resolve
CAPTCHA automaticamente via `transport/captcha_client.py` (ver docstring
desses dois arquivos). As outras dependências de stealth/evasão
(`playwright`, `pyppeteer`, `selenium-stealth`) continuam proibidas — nada
além do que foi pedido foi liberado.
"""

import ast
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "amayama_scraper"

FORBIDDEN_ROOTS = ("selenium", "playwright", "pyppeteer", "requests_html")

#: Únicos arquivos de todo o src/ autorizados a importar uma biblioteca de
#: automação de browser (DEC-007, contracts/browser-transport-contract.md §2;
#: `undetected_chrome_adapter.py` acrescentado por decisão do usuário em
#: 2026-09-10, ver docstring do módulo).
ALLOWED_BROWSER_AUTOMATION_FILES = frozenset(
    {
        SRC_ROOT / "transport" / "chrome_cdp_adapter.py",
        SRC_ROOT / "transport" / "undetected_chrome_adapter.py",
    }
)

#: Dependências de stealth/anti-detecção/evasão ainda proibidas — apenas
#: `undetected-chromedriver` foi liberado (decisão do usuário, 2026-09-10),
#: nada além disso.
FORBIDDEN_STEALTH_DEPENDENCIES = (
    "playwright",
    "pyppeteer",
    "selenium-stealth",
    "selenium_stealth",
)


def _imported_module_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_orchestration_package_has_no_browser_automation_imports():
    files = sorted((SRC_ROOT / "orchestration").rglob("*.py"))
    assert files, "expected files under orchestration/"
    for path in files:
        imported = _imported_module_names(path)
        for forbidden in FORBIDDEN_ROOTS:
            assert not any(
                name == forbidden or name.startswith(forbidden + ".") for name in imported
            ), f"{path} imports forbidden browser-automation module {forbidden!r}"


def test_no_browser_automation_dependency_anywhere_in_src_except_the_allowed_adapters():
    files = sorted(SRC_ROOT.rglob("*.py"))
    for allowed in ALLOWED_BROWSER_AUTOMATION_FILES:
        assert allowed.exists(), f"expected {allowed} to exist"
    for path in files:
        imported = _imported_module_names(path)
        if path in ALLOWED_BROWSER_AUTOMATION_FILES:
            continue
        for forbidden in FORBIDDEN_ROOTS:
            assert not any(
                name == forbidden or name.startswith(forbidden + ".") for name in imported
            ), f"{path} imports forbidden browser-automation module {forbidden!r}"


def test_only_the_allowed_adapters_import_selenium_or_undetected_chromedriver():
    files = sorted(SRC_ROOT.rglob("*.py"))
    importers = {
        path
        for path in files
        if any(
            name == root or name.startswith(root + ".")
            for root in ("selenium", "undetected_chromedriver")
            for name in _imported_module_names(path)
        )
    }
    assert importers == set(ALLOWED_BROWSER_AUTOMATION_FILES)


def test_pyproject_declares_selenium_and_undetected_chromedriver_but_no_other_stealth_dependency():
    pyproject = (SRC_ROOT.parent.parent / "pyproject.toml").read_text(encoding="utf-8")
    assert "selenium" in pyproject.lower(), (
        "expected selenium to be a declared dependency (research.md §14)"
    )
    assert "undetected-chromedriver" in pyproject.lower(), (
        "expected undetected-chromedriver to be a declared dependency "
        "(transport/undetected_chrome_adapter.py, decisão do usuário 2026-09-10)"
    )
    for forbidden in FORBIDDEN_STEALTH_DEPENDENCIES:
        assert forbidden not in pyproject.lower(), (
            f"forbidden dependency {forbidden!r} must never be declared"
        )
