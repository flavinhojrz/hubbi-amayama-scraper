"""T072 — validation/ never contains bypass/solver/evasion logic (Constitution §5, AGENTS.md)."""

import re
from pathlib import Path

VALIDATION_ROOT = Path(__file__).resolve().parents[2] / "src" / "amayama_scraper" / "validation"

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
)


def test_no_forbidden_bypass_terms_in_validation_source() -> None:
    files = sorted(VALIDATION_ROOT.rglob("*.py"))
    assert files, "expected validation/ source files to exist"
    for path in files:
        lowered = path.read_text().lower()
        for pattern in FORBIDDEN_TERMS:
            assert not re.search(pattern, lowered), f"{path} contains forbidden term {pattern!r}"
