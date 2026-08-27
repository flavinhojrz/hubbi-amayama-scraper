"""ResolvedImage (data-model.md §10)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ResolvedImage:
    spec_identity_ref: str
    origin_spec_ref: str
    image_url_or_ref: str
    is_fallback: bool = False
    resolved_within_cluster_key: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("spec_identity_ref", "origin_spec_ref", "image_url_or_ref"):
            value = getattr(self, field_name)
            if not value or not value.strip():
                raise ValueError(f"ResolvedImage.{field_name} must not be empty")
        if self.is_fallback and not self.resolved_within_cluster_key:
            raise ValueError(
                "ResolvedImage.resolved_within_cluster_key is required when is_fallback=True"
            )
