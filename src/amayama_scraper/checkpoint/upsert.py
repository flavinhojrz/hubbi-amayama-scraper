"""upsert_checkpoint() — orquestra transition() (domínio puro) + checkpoint_repo (persistência).

data-model.md §11. PENDING → IN_PROGRESS → ACCEPTED (ou REJECTED, retomável).
`conn` é tipado como `Any` aqui (nunca `sqlite3.Connection`) — checkpoint/
depende diretamente do `checkpoint_repo` concreto (tasks.md T201), mas
nunca importa `sqlite3` (T198 aplica-se apenas ao núcleo agnóstico de
persistência: domain/equivalence/fingerprints/normalization/assets/
snapshots/ingestion — checkpoint/ está fora desse escopo por desenho,
sendo construído já sobre a Phase 10).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from amayama_scraper.checkpoint.checkpoint_entry import (
    CheckpointEntry,
    CheckpointEvent,
    CheckpointStatus,
    transition,
)
from amayama_scraper.persistence.repositories.checkpoint_repo import (
    get_checkpoint_entry,
    upsert_checkpoint_entry,
)


def upsert_checkpoint(
    conn: Any,
    *,
    run_id: str,
    spec_key: str,
    category_slug: str,
    group_id: str,
    event: CheckpointEvent,
    raw_capture_id: str | None = None,
    evidence: dict[str, object] | None = None,
) -> CheckpointEntry:
    current = get_checkpoint_entry(conn, run_id, spec_key, category_slug, group_id)
    current_status = current.status if current is not None else CheckpointStatus.PENDING
    attempt_count = current.attempt_count if current is not None else 0
    new_status = transition(current_status, event)
    now = datetime.now(UTC)

    is_start = event is CheckpointEvent.START_ATTEMPT
    is_accept = event is CheckpointEvent.ACCEPT

    entry = CheckpointEntry(
        run_id=run_id,
        spec_key=spec_key,
        category_slug=category_slug,
        group_id=group_id,
        status=new_status,
        raw_capture_id=(
            raw_capture_id if is_accept else (current.raw_capture_id if current else None)
        ),
        attempt_count=attempt_count + 1 if is_start else attempt_count,
        last_attempt_at=now if is_start else (current.last_attempt_at if current else None),
        completed_at=now if is_accept else (current.completed_at if current else None),
        evidence=evidence if evidence is not None else (current.evidence if current else {}),
    )
    upsert_checkpoint_entry(conn, entry)
    return entry
