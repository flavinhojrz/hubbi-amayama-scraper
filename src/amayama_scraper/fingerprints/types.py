"""FingerprintSet — 4 hashes independentes + versão (data-model.md §7)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FingerprintSet:
    structure_hash: str
    spec_parts_hash: str
    schema_semantic_hash: str
    image_hash: str
    fingerprint_version: str

    def __post_init__(self) -> None:
        for field_name in (
            "structure_hash",
            "spec_parts_hash",
            "schema_semantic_hash",
            "image_hash",
            "fingerprint_version",
        ):
            value = getattr(self, field_name)
            if not value or not value.strip():
                raise ValueError(f"FingerprintSet.{field_name} must not be empty")
