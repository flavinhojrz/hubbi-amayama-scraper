"""compute_fingerprint_set() — agregador versionado (Constitution §13).

fingerprint_version = "amayama-fingerprint-v1".
"""

from __future__ import annotations

from amayama_scraper.fingerprints.image import image_hash
from amayama_scraper.fingerprints.schema_semantic import schema_semantic_hash
from amayama_scraper.fingerprints.spec import AssembledSpecTree, spec_parts_hash
from amayama_scraper.fingerprints.structure import structure_hash
from amayama_scraper.fingerprints.types import FingerprintSet

FINGERPRINT_VERSION = "amayama-fingerprint-v1"


def compute_fingerprint_set(tree: AssembledSpecTree) -> FingerprintSet:
    return FingerprintSet(
        structure_hash=structure_hash(tree),
        spec_parts_hash=spec_parts_hash(tree),
        schema_semantic_hash=schema_semantic_hash(tree),
        image_hash=image_hash(tree),
        fingerprint_version=FINGERPRINT_VERSION,
    )
