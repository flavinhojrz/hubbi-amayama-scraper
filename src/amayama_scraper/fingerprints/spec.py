"""spec_parts_hash() — contracts/normalization-fingerprint-contracts.md "Fingerprints hierárquicos".

Opera sobre a `AssembledSpecTree` (`tuple[Category, ...]`, saída de
`assemble_spec_tree()`, Phase 4). Identidade da spec NUNCA entra aqui —
apenas o conteúdo de peças, via multiset de `category_fingerprint`.
"""

from __future__ import annotations

from amayama_scraper.domain.hierarchy import Category
from amayama_scraper.fingerprints.canonical import domain_hash, multiset_counts
from amayama_scraper.fingerprints.category import category_fingerprint

_DOMAIN_SEPARATOR = "amayama:spec-parts:v1\0"

AssembledSpecTree = tuple[Category, ...]


def spec_parts_hash(tree: AssembledSpecTree) -> str:
    fingerprints = [category_fingerprint(category) for category in tree]
    payload = {"category_fingerprints_multiset": multiset_counts(fingerprints)}
    return domain_hash(_DOMAIN_SEPARATOR, payload)
