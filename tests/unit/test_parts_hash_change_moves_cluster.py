"""T156 — mudança em spec_parts_hash move a spec para outro cluster_key (FR-031, SC-009)."""

from amayama_scraper.equivalence.cluster import cluster_key

SCOPE = "AMAYAMA:VOLKSWAGEN:AMAROK:AMA-BR"


def test_different_spec_parts_hash_produces_different_cluster_key():
    before = cluster_key(
        scope=SCOPE, normalizer_version="v1", fingerprint_version="v1", spec_parts_hash="x" * 64
    )
    after = cluster_key(
        scope=SCOPE, normalizer_version="v1", fingerprint_version="v1", spec_parts_hash="y" * 64
    )
    assert before != after
