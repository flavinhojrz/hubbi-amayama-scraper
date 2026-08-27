"""is_comparison_valid() — contracts/equivalence-contracts.md "Condições de validade".

Interpretação documentada: `SpecSnapshot` não carrega `scope` (é uma
propriedade da `CollectionRun`/feature, não do payload do snapshot) — o
chamador passa `scope_a`/`scope_b` explicitamente (condição 1). As
condições 5 (sem `critical_error`) e 6 (não originado de
CHALLENGE/TRANSLATION_CONTAMINATED) são estruturalmente garantidas pelo
pipeline: um `SpecSnapshot` só existe para capturas `ACCEPTED` (T093), e
`critical_error` de parsing sempre produz `state=INVALID`
(`assign_snapshot_state()`) — por isso `state in {VALID, STALE}` já cobre
as duas condições sem verificação redundante.
"""

from __future__ import annotations

from amayama_scraper.snapshots.snapshot import SnapshotState, SpecSnapshot

_VALID_STATES = frozenset({SnapshotState.VALID, SnapshotState.STALE})


def is_comparison_valid(a: SpecSnapshot, b: SpecSnapshot, *, scope_a: str, scope_b: str) -> bool:
    if scope_a != scope_b:
        return False
    if a.normalizer_version != b.normalizer_version:
        return False
    if a.fingerprint_version != b.fingerprint_version:
        return False
    if not (a.collection_complete and b.collection_complete):
        return False
    return a.state in _VALID_STATES and b.state in _VALID_STATES
