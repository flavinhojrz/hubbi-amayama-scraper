"""accepted_checkpoint_fingerprint() / compute_idempotency_key() — data-model.md §13b.

contracts/snapshot-contract.md, passo 5.
"""

from __future__ import annotations

from amayama_scraper.checkpoint.checkpoint_entry import CheckpointEntry
from amayama_scraper.fingerprints.canonical import domain_hash, multiset_counts

_IDEMPOTENCY_DOMAIN_SEPARATOR = "amayama:snapshot-idempotency:v1\0"


def accepted_checkpoint_fingerprint(
    accepted_entries: tuple[CheckpointEntry, ...] | list[CheckpointEntry],
) -> list[tuple[str, int]]:
    """Multiset determinístico de (category_slug, group_id, raw_capture_id)."""
    triples = [
        f"{entry.category_slug}\0{entry.group_id}\0{entry.raw_capture_id}"
        for entry in accepted_entries
    ]
    return multiset_counts(triples)


def compute_idempotency_key(
    run_id: str,
    spec_key: str,
    accepted_entries: tuple[CheckpointEntry, ...] | list[CheckpointEntry],
) -> str:
    fingerprint = accepted_checkpoint_fingerprint(accepted_entries)
    payload = {
        "run_id": run_id,
        "spec_key": spec_key,
        "accepted_checkpoint_fingerprint": fingerprint,
    }
    return domain_hash(_IDEMPOTENCY_DOMAIN_SEPARATOR, payload)
