"""CurrentSpecState — projeção de leitura, não fonte de verdade (data-model.md §12).

Reconstruível a qualquer momento a partir de SpecSnapshot + ClusterAssignment.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CurrentSpecState:
    spec_identity_ref: str
    latest_snapshot_id: str
    cluster_key: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("spec_identity_ref", "latest_snapshot_id"):
            value = getattr(self, field_name)
            if not value or not value.strip():
                raise ValueError(f"CurrentSpecState.{field_name} must not be empty")
