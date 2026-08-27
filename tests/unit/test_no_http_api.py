"""T244 — export/ não expõe rota HTTP/API — nenhuma dependência de framework web
("Out of Scope")."""

import ast
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "amayama_scraper"

FORBIDDEN_ROOTS = (
    "flask",
    "fastapi",
    "django",
    "starlette",
    "aiohttp",
    "bottle",
    "tornado",
    "uvicorn",
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


def test_export_package_has_no_web_framework_imports():
    files = sorted((SRC_ROOT / "export").rglob("*.py"))
    assert files, "expected files under export/"
    for path in files:
        imported = _imported_module_names(path)
        for forbidden in FORBIDDEN_ROOTS:
            assert not any(
                name == forbidden or name.startswith(forbidden + ".") for name in imported
            ), f"{path} imports forbidden web framework {forbidden!r}"


def test_pyproject_declares_no_web_framework_dependency():
    pyproject = (SRC_ROOT.parent.parent / "pyproject.toml").read_text(encoding="utf-8")
    for forbidden in FORBIDDEN_ROOTS:
        assert forbidden not in pyproject.lower()
