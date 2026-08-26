"""T240 — ExportView preserva identidade, hierarquia, cluster, ResolvedImage e
referência de snapshot sem perda de dado (FR-033)."""

from datetime import UTC, datetime

from amayama_scraper.assets.types import ResolvedImage
from amayama_scraper.domain.hierarchy import Category, Group, Schema
from amayama_scraper.domain.identity import SpecIdentity
from amayama_scraper.domain.part import Part
from amayama_scraper.equivalence.cluster_types import EquivalenceClass
from amayama_scraper.export.boundary import build_export_view
from amayama_scraper.snapshots.snapshot import SnapshotState, SpecSnapshot


def _identity() -> SpecIdentity:
    return SpecIdentity(
        source="AMAYAMA",
        manufacturer="VOLKSWAGEN",
        vehicle_model="AMAROK",
        market="AMA-BR",
        model_code="S7BC8A",
        amayama_catalog_id="62184",
        production_period_raw="2022.06 - ...",
        source_url="https://x/s7bc8a-62184",
    )


def _tree() -> tuple[Category, ...]:
    return (
        Category(
            "engine",
            groups=(Group("1", schemas=(Schema("s1", parts=(Part("s1", "A", oem_code="X"),)),)),),
        ),
    )


def _snapshot() -> SpecSnapshot:
    return SpecSnapshot(
        snapshot_id="snap-1",
        spec_identity_ref=_identity().stable_key(),
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


def test_all_fields_preserved_without_loss():
    identity = _identity()
    tree = _tree()
    snapshot = _snapshot()
    cluster = EquivalenceClass(
        cluster_key="cluster-a",
        scope="AMAYAMA:VOLKSWAGEN:AMAROK:AMA-BR",
        representative_spec_ref=snapshot.spec_identity_ref,
        member_spec_refs=(snapshot.spec_identity_ref, "other-spec"),
    )
    resolved_image = ResolvedImage(
        spec_identity_ref=snapshot.spec_identity_ref,
        origin_spec_ref=snapshot.spec_identity_ref,
        image_url_or_ref="https://x/a.jpg",
        is_fallback=False,
    )

    view = build_export_view(
        identity=identity,
        hierarchy=tree,
        cluster=cluster,
        resolved_image=resolved_image,
        snapshot=snapshot,
    )

    assert view.spec_identity == identity
    assert view.hierarchy == tree
    assert view.cluster is not None
    assert view.cluster.cluster_key == "cluster-a"
    assert view.cluster.is_representative is True
    assert view.resolved_image == resolved_image
    assert view.snapshot_reference.snapshot_id == "snap-1"
    assert view.snapshot_reference.state == SnapshotState.VALID


def test_no_cluster_and_no_image_are_representable_as_none():
    view = build_export_view(
        identity=_identity(),
        hierarchy=_tree(),
        cluster=None,
        resolved_image=None,
        snapshot=_snapshot(),
    )
    assert view.cluster is None
    assert view.resolved_image is None


def test_non_representative_member_is_flagged_correctly():
    identity = _identity()
    snapshot = _snapshot()
    cluster = EquivalenceClass(
        cluster_key="cluster-a",
        scope="AMAYAMA:VOLKSWAGEN:AMAROK:AMA-BR",
        representative_spec_ref="other-spec",
        member_spec_refs=(snapshot.spec_identity_ref, "other-spec"),
    )
    view = build_export_view(
        identity=identity,
        hierarchy=_tree(),
        cluster=cluster,
        resolved_image=None,
        snapshot=snapshot,
    )
    assert view.cluster is not None
    assert view.cluster.is_representative is False
    assert view.cluster.representative_spec_ref == "other-spec"
