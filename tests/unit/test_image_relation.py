"""T139 — image_relation: EXACT/COMPLEMENTARY/DIFFERENT/NONE/UNKNOWN."""

from datetime import UTC, datetime

from amayama_scraper.equivalence.evaluate import evaluate_image_relation
from amayama_scraper.equivalence.types import ImageRelation
from amayama_scraper.fingerprints.image import EMPTY_IMAGE_HASH
from amayama_scraper.snapshots.snapshot import SnapshotState, SpecSnapshot

SCOPE = "AMAYAMA:VOLKSWAGEN:AMAROK:AMA-BR"


def _snapshot(**overrides: object) -> SpecSnapshot:
    defaults: dict[str, object] = dict(
        snapshot_id="snap-1",
        spec_identity_ref="spec-1",
        idempotency_key="idem-1",
        collected_at=datetime.now(UTC),
        parser_version="amayama-parser-v1",
        normalizer_version="amayama-normalizer-v1",
        fingerprint_version="amayama-fingerprint-v1",
        collection_complete=True,
        structure_hash="s" * 64,
        spec_parts_hash="p" * 64,
        schema_semantic_hash="c" * 64,
        image_hash="i" * 64,
        state=SnapshotState.VALID,
    )
    defaults.update(overrides)
    return SpecSnapshot(**defaults)  # type: ignore[arg-type]


def test_both_no_own_images_is_none():
    a = _snapshot(image_hash=EMPTY_IMAGE_HASH)
    b = _snapshot(image_hash=EMPTY_IMAGE_HASH)
    assert evaluate_image_relation(a, b, scope_a=SCOPE, scope_b=SCOPE) is ImageRelation.NONE


def test_identical_own_images_is_exact():
    a = _snapshot(image_hash="x" * 64)
    b = _snapshot(image_hash="x" * 64)
    assert evaluate_image_relation(a, b, scope_a=SCOPE, scope_b=SCOPE) is ImageRelation.EXACT


def test_both_have_images_but_differ_is_different():
    a = _snapshot(image_hash="x" * 64)
    b = _snapshot(image_hash="y" * 64)
    assert evaluate_image_relation(a, b, scope_a=SCOPE, scope_b=SCOPE) is ImageRelation.DIFFERENT


def test_one_side_has_image_same_cluster_is_complementary():
    a = _snapshot(image_hash="x" * 64, spec_parts_hash="same" * 16)
    b = _snapshot(image_hash=EMPTY_IMAGE_HASH, spec_parts_hash="same" * 16)
    assert (
        evaluate_image_relation(a, b, scope_a=SCOPE, scope_b=SCOPE) is ImageRelation.COMPLEMENTARY
    )


def test_one_side_has_image_different_cluster_is_different():
    a = _snapshot(image_hash="x" * 64, spec_parts_hash="p1" * 32)
    b = _snapshot(image_hash=EMPTY_IMAGE_HASH, spec_parts_hash="p2" * 32)
    assert evaluate_image_relation(a, b, scope_a=SCOPE, scope_b=SCOPE) is ImageRelation.DIFFERENT


def test_invalid_comparison_is_unknown():
    a = _snapshot()
    b = _snapshot(state=SnapshotState.INVALID)
    assert evaluate_image_relation(a, b, scope_a=SCOPE, scope_b=SCOPE) is ImageRelation.UNKNOWN
