"""T198 — nenhum módulo de domínio importa sqlite3 (research.md §8/§18, Constitution §6).

Escopo exato de T198: `domain/`, `equivalence/`, `fingerprints/`,
`normalization/`, `assets/`, `snapshots/`, `ingestion/` — ingestion/
depende apenas dos ports (T029), nunca de SQLite concreto. `checkpoint/`
e `orchestration/` (Phases 11/14) dependem diretamente dos repositórios
concretos de `persistence/` por desenho (tasks.md T201/T234 em diante,
construídas já depois da Phase 10 existir) — fora do escopo desta
invariante, que é especificamente sobre o núcleo agnóstico de
transporte/persistência.
"""

import ast
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "amayama_scraper"

DOMAIN_LAYER_PACKAGES = (
    "domain",
    "equivalence",
    "fingerprints",
    "normalization",
    "assets",
    "snapshots",
    "ingestion",
)


def _domain_layer_python_files() -> list[Path]:
    files: list[Path] = []
    for package in DOMAIN_LAYER_PACKAGES:
        files.extend(sorted((SRC_ROOT / package).rglob("*.py")))
    return files


def _all_python_files() -> list[Path]:
    return sorted(SRC_ROOT.rglob("*.py"))


def _is_sqlite3(name: str) -> bool:
    return name == "sqlite3" or name.startswith("sqlite3.")


def _imports_sqlite3(path: Path) -> bool:
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(_is_sqlite3(alias.name) for alias in node.names):
            return True
        if isinstance(node, ast.ImportFrom) and node.module and _is_sqlite3(node.module):
            return True
    return False


def test_domain_layer_never_imports_sqlite3() -> None:
    offenders = [path for path in _domain_layer_python_files() if _imports_sqlite3(path)]
    assert offenders == [], f"sqlite3 imported in domain-layer package: {offenders}"


def test_persistence_actually_uses_sqlite3_sanity_check() -> None:
    # guards against the test above being vacuously true if persistence/
    # ever stopped using sqlite3 for some reason.
    persistence_files = [
        path for path in _all_python_files() if "persistence" in path.relative_to(SRC_ROOT).parts
    ]
    assert any(_imports_sqlite3(path) for path in persistence_files)
