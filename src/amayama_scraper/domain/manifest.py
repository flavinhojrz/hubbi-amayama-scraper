"""SpecGroupManifest — Nível B, fonte autoritativa do universo esperado de groups.

data-model.md §15, research.md §17. Fecha o gap de "quais são todos os
Group esperados" que deixava collection_complete subdefinido.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from amayama_scraper.domain.hierarchy import DuplicateGroupIdError


@dataclass(frozen=True, slots=True)
class ManifestGroupRef:
    group_id: str
    source_url: str

    def __post_init__(self) -> None:
        if not self.group_id or not self.group_id.strip():
            raise ValueError("ManifestGroupRef.group_id must not be empty")
        if not self.source_url or not self.source_url.strip():
            raise ValueError("ManifestGroupRef.source_url must not be empty")


@dataclass(frozen=True, slots=True)
class ManifestCategory:
    category_slug: str
    groups: tuple[ManifestGroupRef, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.category_slug or not self.category_slug.strip():
            raise ValueError("ManifestCategory.category_slug must not be empty")
        seen: set[str] = set()
        for group in self.groups:
            if group.group_id in seen:
                raise DuplicateGroupIdError(
                    f"duplicate group_id {group.group_id!r} "
                    f"in manifest category {self.category_slug!r}"
                )
            seen.add(group.group_id)


@dataclass(frozen=True, slots=True)
class SpecGroupManifest:
    spec_key: str
    source_capture_id: str
    discovered_at: datetime
    categories: tuple[ManifestCategory, ...] = field(default_factory=tuple)
    manifest_complete: bool = False
    validation_evidence: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.spec_key or not self.spec_key.strip():
            raise ValueError("SpecGroupManifest.spec_key must not be empty")
        if not self.source_capture_id or not self.source_capture_id.strip():
            raise ValueError("SpecGroupManifest.source_capture_id must not be empty")

    def expected_group_keys(self) -> frozenset[tuple[str, str]]:
        """The full universe of (category_slug, group_id) expected by this manifest."""
        return frozenset(
            (category.category_slug, group.group_id)
            for category in self.categories
            for group in category.groups
        )


def is_manifest_authoritative(manifest: SpecGroupManifest | None) -> bool:
    """A manifest is authoritative only when fully enumerated without truncation.

    Preconditions 1/2 (source RawCapture ACCEPTED, parser Nível B sem
    critical_error) são responsabilidade de quem constrói/persiste um
    SpecGroupManifest — o parser (contracts/domain-contracts.md "Nível B")
    retorna manifest=None quando falham, então um SpecGroupManifest só
    existe quando já as satisfaz. Precondition 4 (sem group_id duplicado)
    é garantida na construção (ManifestCategory levanta DuplicateGroupIdError).
    Esta função verifica a precondition restante (3): manifest_complete.
    """
    return manifest is not None and manifest.manifest_complete
