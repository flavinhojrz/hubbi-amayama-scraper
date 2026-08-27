"""T239 — orchestration/ não importa nenhuma biblioteca de automação de browser
(Selenium/Playwright/CDP) — DEC-001, "Out of Scope"."""

import ast
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "amayama_scraper"

FORBIDDEN_ROOTS = ("selenium", "playwright", "pyppeteer", "requests_html")


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


def test_no_browser_automation_dependency_anywhere_in_src():
    files = sorted(SRC_ROOT.rglob("*.py"))
    for path in files:
        imported = _imported_module_names(path)
        for forbidden in FORBIDDEN_ROOTS:
            assert not any(
                name == forbidden or name.startswith(forbidden + ".") for name in imported
            ), f"{path} imports forbidden browser-automation module {forbidden!r}"


def test_pyproject_declares_no_browser_automation_dependency():
    pyproject = (SRC_ROOT.parent.parent / "pyproject.toml").read_text(encoding="utf-8")
    for forbidden in ("selenium", "playwright", "pyppeteer"):
        assert forbidden not in pyproject.lower()
