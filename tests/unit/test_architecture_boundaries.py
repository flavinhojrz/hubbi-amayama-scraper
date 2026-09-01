"""T048 — architecture boundary test (FR-006, FR-034; Constitution §6)."""

import ast
from pathlib import Path

import pytest

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "amayama_scraper"

# Modules that must remain free of transport/browser/SQL concerns.
DOMAIN_LAYER_PACKAGES = (
    "domain",
    "normalization",
    "fingerprints",
    "equivalence",
    "assets",
    "snapshots",
    # 003-corpus-analysis-tool — analysis/ computa relatórios sobre dados já
    # carregados por persistence/repositories/*.py; nunca deve importar
    # sqlite3 nem amayama_scraper.persistence diretamente (achado
    # arquitetural do Codex corrigido movendo UNAVAILABLE_HASH para
    # fingerprints/types.py, uma camada neutra que ambos podem importar).
    "analysis",
)

FORBIDDEN_IMPORT_ROOTS = (
    "sqlite3",
    "selenium",
    "playwright",
    "requests",
    "httpx",
    "urllib",
)
FORBIDDEN_INTERNAL_PACKAGES = (
    "amayama_scraper.ingestion",
    "amayama_scraper.persistence",
    "amayama_scraper.orchestration",
)

#: ingestion.ports is the shared dependency-inversion seam itself (pure
#: typing.Protocol + reconstruct_raw_content(), zero concrete I/O) —
#: contracts/ports-contract.md documents it as exactly what
#: snapshots/finalize.py uses to reconstruct raw content from persisted
#: state (research.md §18 "Adendo"). Forbidding the *business logic* of
#: ingestion/ (accept_capture, capture_input, raw_blob, raw_capture,
#: capture_kind, hashing) from the domain layer still holds — only this
#: one already-abstract module is exempted.
ALLOWED_EXCEPTIONS = ("amayama_scraper.ingestion.ports",)


def _python_files(package: str) -> list[Path]:
    return sorted((SRC_ROOT / package).rglob("*.py"))


def _imported_module_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


@pytest.mark.parametrize("package", DOMAIN_LAYER_PACKAGES)
def test_domain_layer_package_has_no_forbidden_imports(package: str) -> None:
    files = _python_files(package)
    assert files, f"expected files under {package}/"
    for path in files:
        imported = _imported_module_names(path)
        for forbidden_root in FORBIDDEN_IMPORT_ROOTS:
            assert not any(
                name == forbidden_root or name.startswith(forbidden_root + ".") for name in imported
            ), f"{path} imports forbidden module rooted at {forbidden_root!r}: {imported}"
        allowed_imported = {name for name in imported if name not in ALLOWED_EXCEPTIONS}
        for forbidden_pkg in FORBIDDEN_INTERNAL_PACKAGES:
            assert not any(
                name == forbidden_pkg or name.startswith(forbidden_pkg + ".")
                for name in allowed_imported
            ), f"{path} imports forbidden internal package {forbidden_pkg!r}: {imported}"


def test_pipeline_never_imports_transport_package() -> None:
    """T013 (002) — orchestration/pipeline.py (núcleo já existente de 001)
    permanece livre de qualquer conhecimento de transporte/Selenium/CDP —
    research.md §5/§13 de 002. `transport/` não está em
    DOMAIN_LAYER_PACKAGES por desenho (é uma folha fora do domínio), então
    esta checagem é explícita em vez de coberta pelo teste parametrizado
    acima."""
    pipeline = SRC_ROOT / "orchestration" / "pipeline.py"
    imported = _imported_module_names(pipeline)
    assert not any(
        name == "amayama_scraper.transport" or name.startswith("amayama_scraper.transport.")
        for name in imported
    ), f"orchestration/pipeline.py must never import amayama_scraper.transport, found: {imported}"


def test_spec_identity_has_no_inferred_vehicle_attribute_fields() -> None:
    import dataclasses

    from amayama_scraper.domain.identity import SpecIdentity

    field_names = {f.name for f in dataclasses.fields(SpecIdentity)}
    for forbidden in ("body", "engine", "drivetrain", "transmission"):
        assert forbidden not in field_names
