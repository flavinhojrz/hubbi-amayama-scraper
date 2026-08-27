"""Category / Group / Schema — hierarquia (data-model.md §2).

Tree-shaped: Category contains Group contains Schema contains Part. This is
the shape assemble_spec_tree() (Phase 4) produces and fingerprints (Phase 6)
consume.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from amayama_scraper.domain.part import Part


class DuplicateGroupIdError(ValueError):
    """Raised when two Group entries within the same Category share group_id.

    Never a silent overwrite (data-model.md §2 invariant) — checked at
    Category construction time, mirroring where the parser (Nível B) must
    also detect it as a critical_error.
    """


@dataclass(frozen=True, slots=True)
class Schema:
    schema_id: str
    parts: tuple[Part, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.schema_id or not self.schema_id.strip():
            raise ValueError("Schema.schema_id must not be empty")


@dataclass(frozen=True, slots=True)
class Group:
    group_id: str
    """Always a string — leading zeros must never be lost to int conversion."""

    schemas: tuple[Schema, ...] = field(default_factory=tuple)
    """Empty is valid and preserved (data-model.md §2 — 'grupos vazios')."""

    def __post_init__(self) -> None:
        if not self.group_id or not self.group_id.strip():
            raise ValueError("Group.group_id must not be empty")


@dataclass(frozen=True, slots=True)
class Category:
    category_slug: str
    groups: tuple[Group, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.category_slug or not self.category_slug.strip():
            raise ValueError("Category.category_slug must not be empty")
        seen: set[str] = set()
        for group in self.groups:
            if group.group_id in seen:
                raise DuplicateGroupIdError(
                    f"duplicate group_id {group.group_id!r} in category {self.category_slug!r}"
                )
            seen.add(group.group_id)
