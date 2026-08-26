"""part_fingerprint() — contracts/normalization-fingerprint-contracts.md "Fingerprint de peça".

Recebe um `Part` bruto (saída de `assemble_spec_tree()`, Phase 4) e aplica
`normalization.version.apply_normalization()` (Phase 5) internamente antes
de montar `canonical_part` — os fingerprints hierárquicos (Phase 6) operam
diretamente sobre a `AssembledSpecTree` bruta (tasks.md T121), então a
normalização acontece neste seam, não antes. `pr_codes` está fora do
`canonical_part` em `amayama-fingerprint-v1` (decisão fechada pelo PO) —
`canonical_part` abaixo é exaustivo, os sete campos listados no contrato e
nenhum outro.
"""

from __future__ import annotations

from amayama_scraper.domain.part import Part
from amayama_scraper.fingerprints.canonical import domain_hash
from amayama_scraper.normalization.version import apply_normalization

_DOMAIN_SEPARATOR = "amayama:part:v1\0"


def part_fingerprint(part: Part) -> str:
    normalized = apply_normalization(part).part
    canonical_part = {
        "schema_id": normalized.schema_id,
        "pnc": normalized.position_pnc,
        "oem": normalized.oem_code,
        "description": normalized.description,
        "details": normalized.details,
        "period": normalized.period_application_text,
        "required": normalized.quantity,
    }
    return domain_hash(_DOMAIN_SEPARATOR, canonical_part)
