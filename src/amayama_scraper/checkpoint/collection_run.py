"""CollectionRun — escopo fixo da execução de coleta (data-model.md §11)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

#: Escopo normativo desta feature (Constitution §2, contracts/equivalence-contracts.md).
FIXED_SCOPE = "AMAYAMA:VOLKSWAGEN:AMAROK:AMA-BR"


class InvalidCollectionRunScopeError(ValueError):
    """CollectionRun.scope divergente do escopo fixo desta feature (FR-001)."""


@dataclass(frozen=True, slots=True)
class CollectionRun:
    run_id: str
    scope: str = FIXED_SCOPE
    started_at: datetime | None = None
    resumed_at: datetime | None = None
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.run_id or not self.run_id.strip():
            raise ValueError("CollectionRun.run_id must not be empty")
        if self.scope != FIXED_SCOPE:
            raise InvalidCollectionRunScopeError(
                f"CollectionRun.scope must be {FIXED_SCOPE!r}, got {self.scope!r}"
            )
