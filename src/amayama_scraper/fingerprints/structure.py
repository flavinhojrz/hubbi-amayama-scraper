"""structure_hash() — contracts/normalization-fingerprint-contracts.md "Fingerprints independentes".

Forma estrutural bruta (categories/groups/schemas), sem conteúdo de
parts — usada por revalidação para localizar o nível de divergência sem
recomputar todos os hashes de conteúdo.
"""

from __future__ import annotations

from amayama_scraper.fingerprints.canonical import domain_hash, multiset_counts
from amayama_scraper.fingerprints.spec import AssembledSpecTree

_DOMAIN_SEPARATOR = "amayama:structure:v1\0"


def structure_hash(tree: AssembledSpecTree) -> str:
    categories = [category.category_slug for category in tree]
    groups = [
        f"{category.category_slug}\0{group.group_id}"
        for category in tree
        for group in category.groups
    ]
    schemas = [
        f"{group.group_id}\0{schema.schema_id}"
        for category in tree
        for group in category.groups
        for schema in group.schemas
    ]
    payload = {
        "categories_multiset": multiset_counts(categories),
        "groups_multiset": multiset_counts(groups),
        "schemas_multiset": multiset_counts(schemas),
    }
    return domain_hash(_DOMAIN_SEPARATOR, payload)
