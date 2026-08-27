"""CheckpointEntry — unidade mínima de progresso retomável (data-model.md §11).

Group é a unidade mínima; category_slug é apenas índice. Chave lógica
única: (run_id, spec_key, category_slug, group_id) — data-model.md §13a.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class CheckpointStatus(StrEnum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class CheckpointEvent(StrEnum):
    START_ATTEMPT = "START_ATTEMPT"
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"


def transition(current: CheckpointStatus, event: CheckpointEvent) -> CheckpointStatus:
    """Pure state transition function (data-model.md §11 "Regras de transição").

    ACCEPTED is terminal within a run — any further event is a no-op
    (mirrors the upsert no-op semantics of §13a), never an error and
    never a regression to another status.
    """
    if current is CheckpointStatus.ACCEPTED:
        return current

    if event is CheckpointEvent.START_ATTEMPT:
        if current in (CheckpointStatus.PENDING, CheckpointStatus.REJECTED):
            return CheckpointStatus.IN_PROGRESS
        return current

    if event is CheckpointEvent.ACCEPT:
        if current is CheckpointStatus.IN_PROGRESS:
            return CheckpointStatus.ACCEPTED
        raise ValueError(f"cannot ACCEPT from status {current}")

    if event is CheckpointEvent.REJECT:
        if current is CheckpointStatus.IN_PROGRESS:
            return CheckpointStatus.REJECTED
        raise ValueError(f"cannot REJECT from status {current}")

    raise ValueError(f"unknown event {event}")  # pragma: no cover - exhaustive enum


@dataclass(frozen=True, slots=True)
class CheckpointEntry:
    run_id: str
    spec_key: str
    category_slug: str
    group_id: str
    status: CheckpointStatus = CheckpointStatus.PENDING
    raw_capture_id: str | None = None
    attempt_count: int = 0
    last_attempt_at: datetime | None = None
    completed_at: datetime | None = None
    evidence: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in ("run_id", "spec_key", "category_slug", "group_id"):
            value = getattr(self, field_name)
            if not value or not value.strip():
                raise ValueError(f"CheckpointEntry.{field_name} must not be empty")
        if self.attempt_count < 0:
            raise ValueError("CheckpointEntry.attempt_count must not be negative")
        if self.status is CheckpointStatus.ACCEPTED and self.completed_at is None:
            raise ValueError("CheckpointEntry.completed_at is required when status is ACCEPTED")

    @property
    def key(self) -> tuple[str, str, str, str]:
        """The unique logical key (data-model.md §13a)."""
        return (self.run_id, self.spec_key, self.category_slug, self.group_id)
