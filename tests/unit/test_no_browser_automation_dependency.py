"""T011/T012 (002) — Selenium/CDP é permitido, mas SOMENTE em
`transport/chrome_cdp_adapter.py` (research.md §13 de 002, DEC-007).

Histórico: T239 (001) afirmava que NENHUM arquivo de `src/` importava
Selenium/Playwright/CDP — correto sob DEC-001 de 001 ("Selenium/CDP
automatizado continua fora do escopo desta feature"). A feature
`002-amarok-ama-br-browser-scraper` É essa automação futura antecipada: o
transporte real por Chrome passa a existir, isolado em um único arquivo. A
invariante original (nenhuma lógica de domínio/parsing/validação/persistência/
orquestração genérica toca Selenium) continua 100% verificada abaixo — apenas
com uma allowlist explícita de um único arquivo, mais precisa que antes, não
mais permissiva. Este teste não foi removido, apenas corrigido de escopo.
"""

import ast
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "amayama_scraper"

FORBIDDEN_ROOTS = ("selenium", "playwright", "pyppeteer", "requests_html")

#: Único arquivo de todo o src/ autorizado a importar uma biblioteca de
#: automação de browser (DEC-007, contracts/browser-transport-contract.md §2).
ALLOWED_BROWSER_AUTOMATION_FILE = SRC_ROOT / "transport" / "chrome_cdp_adapter.py"

#: Dependências de stealth/anti-detecção/evasão — nunca declaradas, em
#: nenhuma circunstância (Constitution §5, spec.md "Segurança arquitetural").
FORBIDDEN_STEALTH_DEPENDENCIES = (
    "playwright",
    "pyppeteer",
    "undetected-chromedriver",
    "undetected_chromedriver",
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


def test_no_browser_automation_dependency_anywhere_in_src_except_the_cdp_adapter():
    files = sorted(SRC_ROOT.rglob("*.py"))
    assert ALLOWED_BROWSER_AUTOMATION_FILE.exists(), (
        "expected the CDP adapter file to exist once T017/T019/T021/T023 (002) are implemented"
    )
    for path in files:
        imported = _imported_module_names(path)
        if path == ALLOWED_BROWSER_AUTOMATION_FILE:
            continue
        for forbidden in FORBIDDEN_ROOTS:
            assert not any(
                name == forbidden or name.startswith(forbidden + ".") for name in imported
            ), f"{path} imports forbidden browser-automation module {forbidden!r}"


def test_cdp_adapter_file_is_the_only_one_importing_selenium():
    files = sorted(SRC_ROOT.rglob("*.py"))
    importers = [
        path
        for path in files
        if any(
            name == "selenium" or name.startswith("selenium.")
            for name in _imported_module_names(path)
        )
    ]
    assert importers == [ALLOWED_BROWSER_AUTOMATION_FILE]


def test_pyproject_declares_selenium_but_no_stealth_or_extra_automation_dependency():
    pyproject = (SRC_ROOT.parent.parent / "pyproject.toml").read_text(encoding="utf-8")
    assert "selenium" in pyproject.lower(), (
        "expected selenium to be a declared dependency (research.md §14)"
    )
    for forbidden in FORBIDDEN_STEALTH_DEPENDENCIES:
        assert forbidden not in pyproject.lower(), (
            f"forbidden dependency {forbidden!r} must never be declared"
        )
