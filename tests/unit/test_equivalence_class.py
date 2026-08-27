"""T042 — EquivalenceClass/ClusterAssignment fields (data-model.md §9)."""

import pytest

from amayama_scraper.equivalence.cluster_types import ClusterAssignment, EquivalenceClass


def test_equivalence_class_holds_members():
    ec = EquivalenceClass(
        cluster_key="cluster-1",
        scope="AMAYAMA:VOLKSWAGEN:AMAROK:AMA-BR",
        representative_spec_ref="spec-a",
        member_spec_refs=("spec-a", "spec-b"),
    )
    assert "spec-b" in ec.member_spec_refs


def test_representative_must_be_a_member():
    with pytest.raises(ValueError):
        EquivalenceClass(
            cluster_key="cluster-1",
            scope="scope",
            representative_spec_ref="spec-x",
            member_spec_refs=("spec-a", "spec-b"),
        )


def test_cluster_assignment_fields():
    assignment = ClusterAssignment(
        spec_identity_ref="spec-a",
        cluster_key="cluster-1",
        normalizer_version="amayama-normalizer-v1",
        fingerprint_version="amayama-fingerprint-v1",
    )
    assert assignment.cluster_key == "cluster-1"
