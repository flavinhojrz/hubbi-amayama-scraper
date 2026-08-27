"""T165 — mudança só de imagem não move a spec para outro parts cluster (FR-030, SC-009).

Integra Phase 6 (image_hash independente de spec_parts_hash), Phase 8
(cluster_key derivado de spec_parts_hash) e Phase 9 (resolve_image).
"""

from amayama_scraper.domain.hierarchy import Category, Group, Schema
from amayama_scraper.domain.part import Part
from amayama_scraper.equivalence.cluster import cluster_key
from amayama_scraper.fingerprints.image import image_hash
from amayama_scraper.fingerprints.spec import spec_parts_hash

SCOPE = "AMAYAMA:VOLKSWAGEN:AMAROK:AMA-BR"


def _tree(image_url: str | None) -> tuple[Category, ...]:
    return (
        Category(
            "engine",
            groups=(
                Group(
                    "1",
                    schemas=(
                        Schema("s1", parts=(Part("s1", "A", oem_code="X", image_url=image_url),)),
                    ),
                ),
            ),
        ),
    )


def test_image_only_change_keeps_the_same_cluster_key():
    tree_before = _tree("https://x/a.jpg")
    tree_after = _tree("https://x/b.jpg")

    parts_hash_before = spec_parts_hash(tree_before)
    parts_hash_after = spec_parts_hash(tree_after)
    assert parts_hash_before == parts_hash_after

    key_before = cluster_key(
        scope=SCOPE,
        normalizer_version="amayama-normalizer-v1",
        fingerprint_version="amayama-fingerprint-v1",
        spec_parts_hash=parts_hash_before,
    )
    key_after = cluster_key(
        scope=SCOPE,
        normalizer_version="amayama-normalizer-v1",
        fingerprint_version="amayama-fingerprint-v1",
        spec_parts_hash=parts_hash_after,
    )
    assert key_before == key_after

    assert image_hash(tree_before) != image_hash(tree_after)
