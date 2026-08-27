"""EquivalenceResult — relações e validade de comparação (data-model.md §8)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class PartsRelation(StrEnum):
    EXACT = "EXACT"
    DIFFERENT = "DIFFERENT"
    UNKNOWN = "UNKNOWN"


class SchemaRelation(StrEnum):
    EXACT = "EXACT"
    DIFFERENT = "DIFFERENT"
    UNKNOWN = "UNKNOWN"


class ImageRelation(StrEnum):
    EXACT = "EXACT"
    COMPLEMENTARY = "COMPLEMENTARY"
    DIFFERENT = "DIFFERENT"
    NONE = "NONE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class EquivalenceResult:
    comparison_valid: bool
    parts_relation: PartsRelation
    schema_relation: SchemaRelation
    image_relation: ImageRelation
