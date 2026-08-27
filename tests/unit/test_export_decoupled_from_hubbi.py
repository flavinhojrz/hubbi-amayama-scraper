"""T243 — export/ não importa nem referencia nenhum schema/pacote específico do
Hubbi (FR-033, "Out of Scope")."""

import ast
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "amayama_scraper"


def test_export_package_never_imports_or_names_a_hubbi_module():
    # docstrings are allowed to explain the decoupling ("não é um schema do
    # ecossistema Hubbi") — what must never appear is an actual import of,
    # or identifier referencing, a hubbi-specific module/package.
    files = sorted((SRC_ROOT / "export").rglob("*.py"))
    assert files, "expected files under export/"
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.append(node.module)
            elif isinstance(node, ast.Name):
                names.append(node.id)
            assert not any("hubbi" in name.lower() for name in names), (
                f"{path} references a hubbi-named import/identifier: {names}"
            )


def test_export_package_imports_only_domain_modules():
    allowed_roots = (
        "amayama_scraper.domain",
        "amayama_scraper.assets",
        "amayama_scraper.equivalence",
        "amayama_scraper.snapshots",
        "amayama_scraper.export",
    )
    files = sorted((SRC_ROOT / "export").rglob("*.py"))
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            module = None
            if isinstance(node, ast.ImportFrom) and node.module:
                module = node.module
            if module is None or not module.startswith("amayama_scraper"):
                continue
            assert any(module == root or module.startswith(root + ".") for root in allowed_roots), (
                f"{path} imports {module!r}, outside allowed domain modules"
            )
