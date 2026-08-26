"""T032 — CollectionRun structural fields + scope (FR-001; data-model.md §11)."""

import pytest

from amayama_scraper.checkpoint.collection_run import (
    FIXED_SCOPE,
    CollectionRun,
    InvalidCollectionRunScopeError,
)


def test_default_scope_is_fixed():
    run = CollectionRun(run_id="run-1")
    assert run.scope == FIXED_SCOPE == "AMAYAMA:VOLKSWAGEN:AMAROK:AMA-BR"


def test_divergent_scope_rejected():
    with pytest.raises(InvalidCollectionRunScopeError):
        CollectionRun(run_id="run-1", scope="AMAYAMA:VOLKSWAGEN:GOLF:AMA-BR")


def test_empty_run_id_rejected():
    with pytest.raises(ValueError):
        CollectionRun(run_id="")
