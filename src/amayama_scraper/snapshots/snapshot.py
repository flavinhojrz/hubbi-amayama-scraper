"""SpecSnapshot — data-model.md §6 (campos), §13c (máquina de estados/idempotência)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from amayama_scraper.checkpoint.checkpoint_entry import CheckpointEntry, CheckpointStatus
from amayama_scraper.domain.manifest import SpecGroupManifest, is_manifest_authoritative


class SnapshotState(StrEnum):
    VALID = "VALID"
    INCOMPLETE = "INCOMPLETE"
    STALE = "STALE"
    SUPERSEDED = "SUPERSEDED"
    INVALID = "INVALID"


@dataclass(frozen=True, slots=True)
class SpecSnapshot:
    snapshot_id: str
    spec_identity_ref: str
    idempotency_key: str
    collected_at: datetime
    parser_version: str
    normalizer_version: str
    fingerprint_version: str
    collection_complete: bool
    structure_hash: str
    spec_parts_hash: str
    schema_semantic_hash: str
    image_hash: str
    state: SnapshotState
    counts: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in (
            "snapshot_id",
            "spec_identity_ref",
            "idempotency_key",
            "parser_version",
            "normalizer_version",
            "fingerprint_version",
            "structure_hash",
            "spec_parts_hash",
            "schema_semantic_hash",
            "image_hash",
        ):
            value = getattr(self, field_name)
            if not value or not value.strip():
                raise ValueError(f"SpecSnapshot.{field_name} must not be empty")


def assign_snapshot_state(*, has_critical_error: bool, collection_complete: bool) -> SnapshotState:
    """FR-027; contracts/snapshot-contract.md "Regras de estado".

    A INVALID (challenge/tradução/HTML inválido) captura nunca chega aqui —
    é filtrada antes, em validation/. This assigns VALID/INCOMPLETE only,
    matching the two paths available once a manifest is authoritative.
    """
    if has_critical_error:
        return SnapshotState.INVALID
    if collection_complete:
        return SnapshotState.VALID
    return SnapshotState.INCOMPLETE


def compute_collection_complete(
    manifest: SpecGroupManifest | None, checkpoint_entries: list[CheckpointEntry]
) -> bool:
    """contracts/snapshot-contract.md; data-model.md §17.

    True se e somente se existe manifesto autoritativo e todo
    (category_slug, group_id) nele listado está ACCEPTED — nunca inferido
    apenas dos CheckpointEntry observados sem manifesto (research.md §17).
    """
    if manifest is None or not is_manifest_authoritative(manifest):
        return False
    accepted_keys = {
        (entry.category_slug, entry.group_id)
        for entry in checkpoint_entries
        if entry.status is CheckpointStatus.ACCEPTED
    }
    return manifest.expected_group_keys() <= accepted_keys


def transition_to_stale(snapshot: SpecSnapshot) -> SpecSnapshot:
    """VALID -> STALE quando a revalidação detecta divergência sem nova captura
    ainda aceita (data-model.md §6 máquina de estados)."""
    if snapshot.state is not SnapshotState.VALID:
        raise ValueError(f"cannot transition to STALE from state {snapshot.state}")
    return SpecSnapshot(
        snapshot_id=snapshot.snapshot_id,
        spec_identity_ref=snapshot.spec_identity_ref,
        idempotency_key=snapshot.idempotency_key,
        collected_at=snapshot.collected_at,
        parser_version=snapshot.parser_version,
        normalizer_version=snapshot.normalizer_version,
        fingerprint_version=snapshot.fingerprint_version,
        collection_complete=snapshot.collection_complete,
        structure_hash=snapshot.structure_hash,
        spec_parts_hash=snapshot.spec_parts_hash,
        schema_semantic_hash=snapshot.schema_semantic_hash,
        image_hash=snapshot.image_hash,
        state=SnapshotState.STALE,
        counts=snapshot.counts,
    )
