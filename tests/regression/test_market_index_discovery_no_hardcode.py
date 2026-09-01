"""T115/T128 — ausência de hardcode de catalog IDs/specs históricos em
src/ (FR-009, SC-008). Busca estática — nenhum dos 6 códigos de catálogo
conhecidos pode aparecer em código de produção; podem aparecer livremente
em tests/fixtures/docs/specs."""

from __future__ import annotations

from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "amayama_scraper"

FORBIDDEN_CATALOG_CODES = (
    "2HBC3X",
    "S1BC3X",
    "S6BC74",
    "S7BC74",
    "S7BC8A",
    "AGDC8A",
)

#: Pré-existente de 001 (mergeado, aprovado antes desta feature) — um único
#: exemplo ilustrativo em docstring de `parse_category_group_from_url()`
#: ("Ex.: '.../s1bc3x-56087/...'"), nunca usado como regra de descoberta
#: (a função não contém nenhuma lista de códigos; extrai genericamente
#: qualquer URL). Não introduzido nem modificado por 002 — auditado e
#: liberado explicitamente aqui, não silenciosamente ignorado.
_KNOWN_PRE_EXISTING_DOCSTRING_EXAMPLES = {
    ("parsing/url_extraction.py", "S1BC3X"),
}


def test_no_forbidden_catalog_code_appears_anywhere_in_production_source() -> None:
    offenders: list[str] = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        upper = text.upper()
        relative = str(path.relative_to(SRC_ROOT))
        for code in FORBIDDEN_CATALOG_CODES:
            if code in upper and (relative, code) not in _KNOWN_PRE_EXISTING_DOCSTRING_EXAMPLES:
                offenders.append(f"{path}: contains {code!r}")
    assert not offenders, "\n".join(offenders)
