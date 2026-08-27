"""normalize_pr_codes() — contracts/normalization-fingerprint-contracts.md.

strip()+upper() por código; lista ordenada lexicograficamente. Aplica-se
para domínio/export/inspeção — pr_codes NÃO entra no part_fingerprint
(contracts/normalization-fingerprint-contracts.md "Fingerprint de peça").
"""

from __future__ import annotations

from amayama_scraper.normalization.text import normalize_text


def normalize_pr_codes(pr_codes: tuple[str, ...]) -> tuple[str, ...]:
    normalized = [normalize_text(code).upper() for code in pr_codes]
    return tuple(sorted(normalized))
