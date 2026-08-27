"""EquivalenceClass / ClusterAssignment (data-model.md §9)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class EquivalenceClass:
    cluster_key: str
    scope: str
    representative_spec_ref: str
    member_spec_refs: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.cluster_key or not self.cluster_key.strip():
            raise ValueError("EquivalenceClass.cluster_key must not be empty")
        if self.representative_spec_ref not in self.member_spec_refs:
            raise ValueError("EquivalenceClass.representative_spec_ref must be a member")


@dataclass(frozen=True, slots=True)
class ClusterAssignment:
    spec_identity_ref: str
    cluster_key: str
    normalizer_version: str
    fingerprint_version: str

    def __post_init__(self) -> None:
        for field_name in (
            "spec_identity_ref",
            "cluster_key",
            "normalizer_version",
            "fingerprint_version",
        ):
            value = getattr(self, field_name)
            if not value or not value.strip():
                raise ValueError(f"ClusterAssignment.{field_name} must not be empty")
