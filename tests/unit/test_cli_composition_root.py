"""T097 — cli/main.py é o único ponto que instancia ChromeCdpTransport
concreto (research.md §5, Constitution §6). orchestration/collection_driver.py
nunca importa transport.chrome_cdp_adapter — depende apenas do Protocol."""

from __future__ import annotations

import ast
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "amayama_scraper"


def _imported_module_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_collection_driver_never_imports_chrome_cdp_adapter() -> None:
    path = SRC_ROOT / "orchestration" / "collection_driver.py"
    imported = _imported_module_names(path)
    assert not any(
        name == "amayama_scraper.transport.chrome_cdp_adapter"
        or name.startswith("amayama_scraper.transport.chrome_cdp_adapter.")
        for name in imported
    )


def test_only_cli_main_imports_chrome_cdp_adapter() -> None:
    files = sorted(SRC_ROOT.rglob("*.py"))
    importers = [
        path
        for path in files
        if any(
            name == "amayama_scraper.transport.chrome_cdp_adapter"
            for name in _imported_module_names(path)
        )
    ]
    assert importers == [SRC_ROOT / "cli" / "main.py"]
