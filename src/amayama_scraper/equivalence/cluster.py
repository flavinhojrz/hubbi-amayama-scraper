"""cluster_key()/build_equivalence_class() — contracts/equivalence-contracts.md "Cluster".

`cluster_key` é a fonte normativa (ponto 14 do PLAN) — qualquer estrutura
auxiliar (DSU/Union-Find) usada futuramente para performance é sempre
recomputável a partir dele, nunca a fonte da verdade.
"""

from __future__ import annotations

import hashlib

from amayama_scraper.equivalence.cluster_types import EquivalenceClass


def cluster_key(
    *, scope: str, normalizer_version: str, fingerprint_version: str, spec_parts_hash: str
) -> str:
    payload = f"{scope}\0{normalizer_version}\0{fingerprint_version}\0{spec_parts_hash}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_equivalence_class(
    *,
    scope: str,
    normalizer_version: str,
    fingerprint_version: str,
    spec_parts_hash: str,
    member_spec_refs: tuple[str, ...],
    representative_spec_ref: str,
) -> EquivalenceClass:
    key = cluster_key(
        scope=scope,
        normalizer_version=normalizer_version,
        fingerprint_version=fingerprint_version,
        spec_parts_hash=spec_parts_hash,
    )
    return EquivalenceClass(
        cluster_key=key,
        scope=scope,
        representative_spec_ref=representative_spec_ref,
        member_spec_refs=member_spec_refs,
    )
