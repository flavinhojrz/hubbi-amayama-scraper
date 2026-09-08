"""T072 — validation/ never contains bypass/solver/evasion logic (Constitution §5, AGENTS.md).

T129 (002) — a mesma auditoria é estendida a transport/, cli/ e aos novos
arquivos de orchestration/ desta feature (a superfície onde bypass/stealth/
evasão faria sentido tentar, se alguém tentasse — spec.md "Segurança
arquitetural"). validation/ permanece coberto pelo teste original."""

import re
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "amayama_scraper"
VALIDATION_ROOT = SRC_ROOT / "validation"

#: T129 (002) — superfície nova desta feature: transporte real por Chrome/CDP
#: e a orquestração/CLI que o compõem.
NEW_FEATURE_AUDIT_ROOTS = (
    SRC_ROOT / "transport",
    SRC_ROOT / "cli",
    SRC_ROOT / "orchestration",
)

# Word-boundary matched — deliberately excludes "solver" as a bare English word
# match inside Portuguese prose (e.g. "resolver"); \b relies on word chars so
# hyphen/underscore variants are listed explicitly.
FORBIDDEN_TERMS = (
    r"\bsolver\b",
    r"\bbypass\b",
    r"\bundetected[-_]chromedriver\b",
    r"\bstealth\b",
    r"\bcaptcha_solve\b",
    r"\banti[-_]detect\b",
    r"\b2captcha\b",
    r"\banticaptcha\b",
    r"\bfingerprint[-_]spoof\b",
    r"\bproxy[-_]rotat\w*\b",
)


def _assert_no_forbidden_terms(files: list[Path]) -> None:
    assert files, "expected source files to exist"
    for path in files:
        lowered = path.read_text(encoding="utf-8").lower()
        for pattern in FORBIDDEN_TERMS:
            assert not re.search(pattern, lowered), f"{path} contains forbidden term {pattern!r}"


def test_no_forbidden_bypass_terms_in_validation_source() -> None:
    _assert_no_forbidden_terms(sorted(VALIDATION_ROOT.rglob("*.py")))


def test_no_forbidden_bypass_terms_in_002_transport_cli_orchestration_source() -> None:
    files = [p for root in NEW_FEATURE_AUDIT_ROOTS for p in sorted(root.rglob("*.py"))]
    _assert_no_forbidden_terms(files)
