"""T238 — orchestration/ não duplica lógica de domínio: chama apenas funções de
validation/, parsing/, normalization/, fingerprints/, equivalence/, assets/,
snapshots/, checkpoint/, persistence/, sem reimplementar regras (Constitution §6)."""

import ast
from pathlib import Path

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

#: no if/elif/else chains keyed on business-meaning string literals (a sign
#: that a rule from validation/parsing/etc. was reimplemented here instead
#: of called) — only CaptureKind enum comparisons are expected.
FORBIDDEN_LITERAL_BRANCHES = ("CHALLENGE", "TRANSLATION_CONTAMINATED", "INCOMPLETE", "REJECTED")


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_orchestration_only_imports_from_domain_modules_or_stdlib():
    pipeline = SRC_ROOT / "orchestration" / "pipeline.py"
    tree = ast.parse(_source(pipeline), filename=str(pipeline))
    for node in ast.walk(tree):
        module = None
        if isinstance(node, ast.ImportFrom) and node.module:
            module = node.module
        if module is None or not module.startswith("amayama_scraper"):
            continue
        assert any(module == root or module.startswith(root + ".") for root in ALLOWED_ROOTS), (
            f"orchestration/pipeline.py imports {module!r}, outside the allowed domain modules"
        )


def test_orchestration_never_hardcodes_validation_outcome_string_literals():
    # ValidationOutcome enum values must be referenced via the enum, never
    # duplicated as bare string literals — that would be reimplementing the
    # DEC-003 precedence logic instead of calling classify_capture().
    pipeline_src = _source(SRC_ROOT / "orchestration" / "pipeline.py")
    for literal in FORBIDDEN_LITERAL_BRANCHES:
        assert f'"{literal}"' not in pipeline_src
        assert f"'{literal}'" not in pipeline_src
