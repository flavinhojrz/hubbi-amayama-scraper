"""T145 — cluster_key() determinístico (scope+normalizer+fingerprint+spec_parts_hash)."""

import hashlib

from amayama_scraper.equivalence.cluster import cluster_key

SCOPE = "AMAYAMA:VOLKSWAGEN:AMAROK:AMA-BR"


def test_matches_documented_formula():
    expected = hashlib.sha256(
        f"{SCOPE}\0amayama-normalizer-v1\0amayama-fingerprint-v1\0{'x' * 64}".encode()
    ).hexdigest()
    actual = cluster_key(
        scope=SCOPE,
        normalizer_version="amayama-normalizer-v1",
        fingerprint_version="amayama-fingerprint-v1",
        spec_parts_hash="x" * 64,
    )
    assert actual == expected


def test_deterministic():
    kwargs = dict(
        scope=SCOPE,
        normalizer_version="amayama-normalizer-v1",
        fingerprint_version="amayama-fingerprint-v1",
        spec_parts_hash="x" * 64,
    )
    assert cluster_key(**kwargs) == cluster_key(**kwargs)


def test_different_spec_parts_hash_changes_cluster_key():
    a = cluster_key(
        scope=SCOPE,
        normalizer_version="v1",
        fingerprint_version="v1",
        spec_parts_hash="x" * 64,
    )
    b = cluster_key(
        scope=SCOPE,
        normalizer_version="v1",
        fingerprint_version="v1",
        spec_parts_hash="y" * 64,
    )
    assert a != b
