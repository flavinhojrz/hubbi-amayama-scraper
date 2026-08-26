"""T046 — CurrentSpecState projection fields (data-model.md §12)."""

import pytest

from amayama_scraper.domain.current_state import CurrentSpecState


def test_holds_latest_snapshot_and_cluster():
    state = CurrentSpecState(
        spec_identity_ref="spec-a", latest_snapshot_id="snap-1", cluster_key="cluster-1"
    )
    assert state.latest_snapshot_id == "snap-1"
    assert state.cluster_key == "cluster-1"


def test_cluster_key_optional():
    state = CurrentSpecState(spec_identity_ref="spec-a", latest_snapshot_id="snap-1")
    assert state.cluster_key is None


def test_required_fields():
    with pytest.raises(ValueError):
        CurrentSpecState(spec_identity_ref="", latest_snapshot_id="snap-1")
