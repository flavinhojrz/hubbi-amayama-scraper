"""T032 — CollectionRun structural fields + scope (FR-001; data-model.md §11).

Atualizado pela evolução multi-modelo (002): `scope` deixou de ser um único
literal fixo. `FIXED_SCOPE` continua existindo apenas como o default
histórico (Amarok/AMA-BR) de `CollectionRun.scope`, preservando
compatibilidade com callers que não passam `scope` explicitamente — não é
mais o único valor aceito (ver checkpoint/collection_run.py).
"""

import pytest

from amayama_scraper.checkpoint.collection_run import FIXED_SCOPE, CollectionRun


def test_default_scope_is_fixed():
    run = CollectionRun(run_id="run-1")
    assert run.scope == FIXED_SCOPE == "AMAYAMA:VOLKSWAGEN:AMAROK:AMA-BR"


def test_other_model_scope_is_accepted():
    run = CollectionRun(run_id="run-1", scope="AMAYAMA:VOLKSWAGEN:GOLF:AMA-BR")
    assert run.scope == "AMAYAMA:VOLKSWAGEN:GOLF:AMA-BR"


def test_empty_run_id_rejected():
    with pytest.raises(ValueError):
        CollectionRun(run_id="")


def test_empty_scope_rejected():
    with pytest.raises(ValueError):
        CollectionRun(run_id="run-1", scope="")
