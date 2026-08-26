"""T208 — CollectionRun.scope fixo rejeita escopo divergente (FR-001, ponto 13 do PLAN)."""

import pytest

from amayama_scraper.checkpoint.collection_run import (
    FIXED_SCOPE,
    CollectionRun,
    InvalidCollectionRunScopeError,
)


def test_default_scope_matches_the_fixed_constant():
    run = CollectionRun(run_id="run-1")
    assert run.scope == FIXED_SCOPE == "AMAYAMA:VOLKSWAGEN:AMAROK:AMA-BR"


def test_divergent_scope_is_rejected():
    with pytest.raises(InvalidCollectionRunScopeError):
        CollectionRun(run_id="run-1", scope="AMAYAMA:VOLKSWAGEN:AMAROK:AMA-US")
