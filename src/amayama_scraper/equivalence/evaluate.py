"""evaluate_*_relation()/can_deduplicate() — contracts/equivalence-contracts.md "Relações".

`evaluate_image_relation()` — interpretação documentada (composição, sem
inventar categoria nova): `COMPLEMENTARY` é usado exatamente como definido
no contrato — um lado com imagem própria, o outro sem, **dentro de um
cluster de peças já comprovado** (`parts_relation == EXACT`). Quando
exatamente um lado tem imagem própria mas os dois NÃO estão no mesmo
cluster comprovado (`parts_relation != EXACT`), o contrato não nomeia essa
combinação explicitamente — nenhuma relação de complementaridade foi
comprovada, então é tratada como `DIFFERENT` (mais próxima semanticamente
de "situação de imagem diverge, sem fallback justificado") em vez de
inventar uma sexta categoria.
"""

from __future__ import annotations

from amayama_scraper.equivalence.types import (
    EquivalenceResult,
    ImageRelation,
    PartsRelation,
    SchemaRelation,
)
from amayama_scraper.equivalence.validity import is_comparison_valid
from amayama_scraper.fingerprints.image import EMPTY_IMAGE_HASH
from amayama_scraper.snapshots.snapshot import SpecSnapshot


def evaluate_parts_relation(
    a: SpecSnapshot, b: SpecSnapshot, *, scope_a: str, scope_b: str
) -> PartsRelation:
    if not is_comparison_valid(a, b, scope_a=scope_a, scope_b=scope_b):
        return PartsRelation.UNKNOWN
    if a.spec_parts_hash == b.spec_parts_hash:
        return PartsRelation.EXACT
    return PartsRelation.DIFFERENT


def evaluate_schema_relation(
    a: SpecSnapshot, b: SpecSnapshot, *, scope_a: str, scope_b: str
) -> SchemaRelation:
    if not is_comparison_valid(a, b, scope_a=scope_a, scope_b=scope_b):
        return SchemaRelation.UNKNOWN
    if a.schema_semantic_hash == b.schema_semantic_hash:
        return SchemaRelation.EXACT
    return SchemaRelation.DIFFERENT


def evaluate_image_relation(
    a: SpecSnapshot, b: SpecSnapshot, *, scope_a: str, scope_b: str
) -> ImageRelation:
    if not is_comparison_valid(a, b, scope_a=scope_a, scope_b=scope_b):
        return ImageRelation.UNKNOWN

    a_has_own_images = a.image_hash != EMPTY_IMAGE_HASH
    b_has_own_images = b.image_hash != EMPTY_IMAGE_HASH

    if not a_has_own_images and not b_has_own_images:
        return ImageRelation.NONE

    if a_has_own_images and b_has_own_images:
        if a.image_hash == b.image_hash:
            return ImageRelation.EXACT
        return ImageRelation.DIFFERENT

    # exactly one side has own images
    parts_relation = evaluate_parts_relation(a, b, scope_a=scope_a, scope_b=scope_b)
    if parts_relation is PartsRelation.EXACT:
        return ImageRelation.COMPLEMENTARY
    return ImageRelation.DIFFERENT


def evaluate_equivalence(
    a: SpecSnapshot, b: SpecSnapshot, *, scope_a: str, scope_b: str
) -> EquivalenceResult:
    return EquivalenceResult(
        comparison_valid=is_comparison_valid(a, b, scope_a=scope_a, scope_b=scope_b),
        parts_relation=evaluate_parts_relation(a, b, scope_a=scope_a, scope_b=scope_b),
        schema_relation=evaluate_schema_relation(a, b, scope_a=scope_a, scope_b=scope_b),
        image_relation=evaluate_image_relation(a, b, scope_a=scope_a, scope_b=scope_b),
    )


def can_deduplicate(a: SpecSnapshot, b: SpecSnapshot, *, scope_a: str, scope_b: str) -> bool:
    """FR-019, FR-020: apenas hash exato prova equivalência — nunca heurística."""
    valid = is_comparison_valid(a, b, scope_a=scope_a, scope_b=scope_b)
    relation = evaluate_parts_relation(a, b, scope_a=scope_a, scope_b=scope_b)
    return valid and relation is PartsRelation.EXACT
