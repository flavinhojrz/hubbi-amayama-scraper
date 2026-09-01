"""T238 — orchestration/ não duplica lógica de domínio: chama apenas funções de
validation/, parsing/, normalization/, fingerprints/, equivalence/, assets/,
snapshots/, checkpoint/, persistence/, sem reimplementar regras (Constitution §6).

T116 (002) — estende a mesma verificação aos novos arquivos de orchestration/
(collection_driver.py, run_selection.py, retry_classification.py, dry_run.py,
progress_reporter.py), com `amayama_scraper.transport` (o Protocol, nunca o
adapter — pipeline.py continua coberto separadamente e continua proibido de
importar transport, ver test_architecture_boundaries.py) e
`amayama_scraper.orchestration` (referências entre os próprios submódulos
novos) adicionados à allowlist SOMENTE para estes arquivos novos —
pipeline.py permanece coberto pelo teste original, sem essa ampliação."""

import ast
from pathlib import Path

import pytest

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "amayama_scraper"

ALLOWED_ROOTS = (
    "amayama_scraper.validation",
    "amayama_scraper.parsing",
    "amayama_scraper.normalization",
    "amayama_scraper.fingerprints",
    "amayama_scraper.equivalence",
    "amayama_scraper.assets",
    "amayama_scraper.snapshots",
    "amayama_scraper.checkpoint",
    "amayama_scraper.persistence",
    "amayama_scraper.ingestion",
    "amayama_scraper.domain",
)

#: T116 (002) — únicos dois roots adicionais, e somente para os arquivos
#: novos abaixo: o Protocol de transporte (nunca o adapter concreto — isso
#: é verificado à parte por test_cli_composition_root.py/
#: test_architecture_boundaries.py) e o próprio pacote orchestration (para
#: as referências entre collection_driver.py <-> pipeline.py/
#: retry_classification.py/progress_reporter.py).
NEW_FILES_EXTRA_ALLOWED_ROOTS = ALLOWED_ROOTS + (
    "amayama_scraper.transport.port",
    "amayama_scraper.transport.errors",
    "amayama_scraper.orchestration",
)

NEW_ORCHESTRATION_FILES = (
    "collection_driver.py",
    "run_selection.py",
    "retry_classification.py",
    "dry_run.py",
    "progress_reporter.py",
)

#: no if/elif/else chains keyed on business-meaning string literals (a sign
#: that a rule from validation/parsing/etc. was reimplemented here instead
#: of called) — only CaptureKind enum comparisons are expected.
FORBIDDEN_LITERAL_BRANCHES = ("CHALLENGE", "TRANSLATION_CONTAMINATED", "INCOMPLETE", "REJECTED")


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _assert_only_imports_from(path: Path, allowed_roots: tuple[str, ...]) -> None:
    tree = ast.parse(_source(path), filename=str(path))
    for node in ast.walk(tree):
        module = None
        if isinstance(node, ast.ImportFrom) and node.module:
            module = node.module
        if module is None or not module.startswith("amayama_scraper"):
            continue
        assert any(module == root or module.startswith(root + ".") for root in allowed_roots), (
            f"{path} imports {module!r}, outside the allowed domain modules"
        )


def test_orchestration_only_imports_from_domain_modules_or_stdlib():
    _assert_only_imports_from(SRC_ROOT / "orchestration" / "pipeline.py", ALLOWED_ROOTS)


@pytest.mark.parametrize("filename", NEW_ORCHESTRATION_FILES)
def test_new_orchestration_files_only_import_from_domain_modules_transport_port_or_orchestration(
    filename: str,
) -> None:
    _assert_only_imports_from(SRC_ROOT / "orchestration" / filename, NEW_FILES_EXTRA_ALLOWED_ROOTS)


def test_orchestration_never_hardcodes_validation_outcome_string_literals():
    # ValidationOutcome enum values must be referenced via the enum, never
    # duplicated as bare string literals — that would be reimplementing the
    # DEC-003 precedence logic instead of calling classify_capture().
    pipeline_src = _source(SRC_ROOT / "orchestration" / "pipeline.py")
    for literal in FORBIDDEN_LITERAL_BRANCHES:
        assert f'"{literal}"' not in pipeline_src
        assert f"'{literal}'" not in pipeline_src
