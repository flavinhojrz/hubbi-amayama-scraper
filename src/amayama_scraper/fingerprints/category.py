"""category_fingerprint() — contracts/normalization-fingerprint-contracts.md.

Multiset de `group_fingerprint` sobre todos os groups da category (grupos
vazios entram normalmente, com seu próprio group_fingerprint).
"""

from __future__ import annotations

from amayama_scraper.domain.hierarchy import Category
from amayama_scraper.fingerprints.canonical import domain_hash, multiset_counts
from amayama_scraper.fingerprints.group import group_fingerprint

_DOMAIN_SEPARATOR = "amayama:category:v1\0"


def category_fingerprint(category: Category) -> str:
    fingerprints = [group_fingerprint(group) for group in category.groups]
    payload = {
        "category_slug": category.category_slug,
        "group_fingerprints_multiset": multiset_counts(fingerprints),
    }
    return domain_hash(_DOMAIN_SEPARATOR, payload)
