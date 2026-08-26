"""image_hash() — contracts/normalization-fingerprint-contracts.md "Fingerprints independentes".

Multiset de referências de imagem PRÓPRIAS da árvore (`Part.image_url`,
como capturado — nenhum fallback/herança entra aqui: fallback só existe
depois da resolução de equivalência/cluster, contracts/image-contract.md,
Phase 9). NUNCA entra em `spec_parts_hash` nem influencia `parts_relation`
(Constitution §8, §10, FR-018, FR-030, SC-009).
"""

from __future__ import annotations

from amayama_scraper.fingerprints.canonical import domain_hash, multiset_counts
from amayama_scraper.fingerprints.spec import AssembledSpecTree
from amayama_scraper.normalization.text import normalize_text

_DOMAIN_SEPARATOR = "amayama:image:v1\0"


def image_hash(tree: AssembledSpecTree) -> str:
    refs = [
        normalize_text(part.image_url)
        for category in tree
        for group in category.groups
        for schema in group.schemas
        for part in schema.parts
        if part.image_url
    ]
    payload = {"own_image_refs_multiset": multiset_counts(refs)}
    return domain_hash(_DOMAIN_SEPARATOR, payload)


#: image_hash() of an empty own-image multiset — the fixed value produced
#: whenever a spec has no own images at all. Used by equivalence/evaluate.py
#: to distinguish "has own images" from "has none" from the hash alone.
EMPTY_IMAGE_HASH = image_hash(())
