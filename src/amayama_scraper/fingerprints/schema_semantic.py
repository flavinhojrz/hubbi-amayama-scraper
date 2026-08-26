"""schema_semantic_hash() — contracts/normalization-fingerprint-contracts.md.

Multiset de `schema_id` normalizado — baseado na estrutura/identificação
de schemas, não no conteúdo de parts. Independente de `spec_parts_hash`.
"""

from __future__ import annotations

from amayama_scraper.fingerprints.canonical import domain_hash, multiset_counts
from amayama_scraper.fingerprints.spec import AssembledSpecTree
from amayama_scraper.normalization.identifiers import normalize_schema_id

_DOMAIN_SEPARATOR = "amayama:schema-semantic:v1\0"


def schema_semantic_hash(tree: AssembledSpecTree) -> str:
    schema_ids = [
        normalize_schema_id(schema.schema_id)
        for category in tree
        for group in category.groups
        for schema in group.schemas
    ]
    payload = {"schemas_multiset": multiset_counts(schema_ids)}
    return domain_hash(_DOMAIN_SEPARATOR, payload)
