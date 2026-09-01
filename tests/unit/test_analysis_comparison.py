"""T018 — compare_specs(): par EXACT, diff de grupos via manifest, lado sem snapshot."""

from datetime import UTC, datetime

from amayama_scraper.analysis.comparison import compare_specs
from amayama_scraper.analysis.types import HashComparisonState, ScopeIdentifier
from amayama_scraper.domain.identity import SpecIdentity
from amayama_scraper.domain.manifest import ManifestCategory, ManifestGroupRef, SpecGroupManifest
from amayama_scraper.equivalence.types import PartsRelation
from amayama_scraper.persistence.repositories.snapshot_repo import UNAVAILABLE_HASH
from amayama_scraper.snapshots.snapshot import SnapshotState, SpecSnapshot

SCOPE = ScopeIdentifier(manufacturer="VOLKSWAGEN", vehicle_model="AMAROK", market="AMA-BR")


def _identity(model_code: str, *, market: str = "AMA-BR") -> SpecIdentity:
    return SpecIdentity(
        source="AMAYAMA",
        manufacturer="VOLKSWAGEN",
        vehicle_model="AMAROK",
        market=market,
        model_code=model_code,
        amayama_catalog_id="999",
        production_period_raw="2020-2021",
        source_url=f"https://amayama.example/{model_code}",
    )


def _snapshot(
    spec_ref: str,
    *,
    spec_parts_hash: str,
    structure_hash: str = "s" * 64,
    schema_semantic_hash: str = "c" * 64,
    image_hash: str = "i" * 64,
) -> SpecSnapshot:
    return SpecSnapshot(
        snapshot_id=f"snap-{spec_ref[:8]}",
        spec_identity_ref=spec_ref,
        idempotency_key=f"idem-{spec_ref[:8]}",
        collected_at=datetime(2026, 1, 1, tzinfo=UTC),
        parser_version="p1",
        normalizer_version="amayama-normalizer-v1",
        fingerprint_version="amayama-fingerprint-v1",
        collection_complete=True,
        structure_hash=structure_hash,
        spec_parts_hash=spec_parts_hash,
        schema_semantic_hash=schema_semantic_hash,
        image_hash=image_hash,
        state=SnapshotState.VALID,
        counts={"categories": 1, "groups": 2, "schemas": 5, "parts": 50},
    )


def _manifest(spec_key: str, group_ids: list[str]) -> SpecGroupManifest:
    return SpecGroupManifest(
        spec_key=spec_key,
        source_capture_id="cap-1",
        discovered_at=datetime(2026, 1, 1, tzinfo=UTC),
        categories=(
            ManifestCategory(
                category_slug="engine",
                groups=tuple(
                    ManifestGroupRef(group_id=g, source_url=f"https://x/{g}") for g in group_ids
                ),
            ),
        ),
        manifest_complete=True,
    )


def test_exact_parts_hash_pair_reports_exact_relation():
    spec_a = _identity("C1")
    spec_b = _identity("C2")
    same_hash = "h" * 64
    snapshot_a = _snapshot(spec_a.stable_key(), spec_parts_hash=same_hash)
    snapshot_b = _snapshot(spec_b.stable_key(), spec_parts_hash=same_hash)

    comparison = compare_specs(SCOPE, spec_a, spec_b, snapshot_a, snapshot_b, None, None)

    assert comparison.equivalence is not None
    assert comparison.equivalence.parts_relation is PartsRelation.EXACT
    assert comparison.equivalence.comparison_valid is True
    assert comparison.hash_comparison.spec_parts_hash is HashComparisonState.EQUAL


def test_group_diff_via_manifest_reports_exclusive_and_shared_groups():
    spec_a = _identity("C3")
    spec_b = _identity("C4")
    manifest_a = _manifest(spec_a.stable_key(), ["1", "2", "3"])
    manifest_b = _manifest(spec_b.stable_key(), ["2", "3", "4"])

    comparison = compare_specs(SCOPE, spec_a, spec_b, None, None, manifest_a, manifest_b)

    assert comparison.group_diff is not None
    assert comparison.group_diff.only_in_a == {("engine", "1")}
    assert comparison.group_diff.only_in_b == {("engine", "4")}
    assert comparison.group_diff.shared == {("engine", "2"), ("engine", "3")}


def test_missing_snapshot_on_one_side_reports_unavailable_not_exception():
    spec_a = _identity("C5")
    spec_b = _identity("C6")
    snapshot_a = _snapshot(spec_a.stable_key(), spec_parts_hash="h" * 64)

    comparison = compare_specs(SCOPE, spec_a, spec_b, snapshot_a, None, None, None)

    assert comparison.equivalence is None
    assert comparison.equivalence_unavailable_reason is not None
    assert comparison.counts_a is not None
    assert comparison.counts_b is None


def test_parts_diff_is_always_reported_as_unavailable():
    spec_a = _identity("C7")
    spec_b = _identity("C8")

    comparison = compare_specs(SCOPE, spec_a, spec_b, None, None, None, None)

    assert comparison.parts_diff_available is False
    assert comparison.parts_diff_unavailable_reason


def test_cross_scope_specs_with_identical_hashes_are_invalid_not_equal():
    """Codex finding #1 — duas specs de mercados diferentes com o MESMO
    spec_parts_hash nunca podem ser reportadas como equivalentes: scope_a e
    scope_b precisam ser derivados de cada spec, não de um scope compartilhado."""
    spec_a = _identity("C9", market="AMA-BR")
    spec_b = _identity("C10", market="AMA-OTHER")
    same_hash = "h" * 64
    snapshot_a = _snapshot(spec_a.stable_key(), spec_parts_hash=same_hash)
    snapshot_b = _snapshot(spec_b.stable_key(), spec_parts_hash=same_hash)

    # O `scope` externo passado aqui é o mesmo para os dois lados de propósito
    # (reflete o que a CLI faz hoje, derivando de identity_a) — o teste prova
    # que compare_specs() não confia nele para decidir validade.
    comparison = compare_specs(SCOPE, spec_a, spec_b, snapshot_a, snapshot_b, None, None)

    assert comparison.equivalence is not None
    assert comparison.equivalence.comparison_valid is False
    assert comparison.equivalence.parts_relation is PartsRelation.UNKNOWN
    assert comparison.hash_comparison.spec_parts_hash is HashComparisonState.UNAVAILABLE
    assert comparison.hash_comparison.structure_hash is HashComparisonState.UNAVAILABLE


def test_hash_comparison_reports_only_structure_hash_as_different():
    """Codex finding #3 — os 4 hashes são expostos individualmente; aqui só
    structure_hash diverge, os outros 3 devem ser EQUAL."""
    spec_a = _identity("C11")
    spec_b = _identity("C12")
    snapshot_a = _snapshot(
        spec_a.stable_key(), spec_parts_hash="h" * 64, structure_hash="aaaa" * 16
    )
    snapshot_b = _snapshot(
        spec_b.stable_key(), spec_parts_hash="h" * 64, structure_hash="bbbb" * 16
    )

    comparison = compare_specs(SCOPE, spec_a, spec_b, snapshot_a, snapshot_b, None, None)

    hc = comparison.hash_comparison
    assert hc.structure_hash is HashComparisonState.DIFFERENT
    assert hc.spec_parts_hash is HashComparisonState.EQUAL
    assert hc.schema_semantic_hash is HashComparisonState.EQUAL
    assert hc.image_hash is HashComparisonState.EQUAL


def test_unavailable_fingerprint_on_one_side_marks_only_that_hash_unavailable():
    """Codex finding #5 — um hash NULL (UNAVAILABLE_HASH) nunca é comparado
    como igual/diferente; os demais hashes, se comparáveis, continuam normais."""
    spec_a = _identity("C13")
    spec_b = _identity("C14")
    snapshot_a = _snapshot(
        spec_a.stable_key(), spec_parts_hash="h" * 64, image_hash=UNAVAILABLE_HASH
    )
    snapshot_b = _snapshot(spec_b.stable_key(), spec_parts_hash="h" * 64)

    comparison = compare_specs(SCOPE, spec_a, spec_b, snapshot_a, snapshot_b, None, None)

    hc = comparison.hash_comparison
    assert hc.image_hash is HashComparisonState.UNAVAILABLE
    assert hc.spec_parts_hash is HashComparisonState.EQUAL
    assert hc.structure_hash is HashComparisonState.EQUAL
