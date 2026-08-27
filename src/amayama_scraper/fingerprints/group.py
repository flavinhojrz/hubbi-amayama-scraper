"""group_fingerprint() — contracts/normalization-fingerprint-contracts.md.

Multiset de `part_fingerprint` sobre TODAS as parts de TODOS os schemas do
group (schema_id já participa de cada `part_fingerprint` individual — não
é re-adicionado aqui). Um group vazio ainda produz um fingerprint válido
(multiset vazio) — grupos vazios não são omitidos (data-model.md §2).
"""

from __future__ import annotations

from amayama_scraper.domain.hierarchy import Group
from amayama_scraper.fingerprints.canonical import domain_hash, multiset_counts
from amayama_scraper.fingerprints.part import part_fingerprint

_DOMAIN_SEPARATOR = "amayama:group:v1\0"


def group_fingerprint(group: Group) -> str:
    fingerprints = [part_fingerprint(part) for schema in group.schemas for part in schema.parts]
    payload = {
        "group_id": group.group_id,
        "part_fingerprints_multiset": multiset_counts(fingerprints),
    }
    return domain_hash(_DOMAIN_SEPARATOR, payload)
