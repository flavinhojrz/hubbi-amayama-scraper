"""T208 (histórico) — atualizado pela evolução multi-modelo (002) e pela
correção de robustez arquitetural (004): CollectionRun.scope não é mais
fixo em código. Ele é derivado deterministicamente de um CollectionContext
(domain/collection_context.py) — canônico, validado e sem colisão."""

from amayama_scraper.checkpoint.collection_run import FIXED_SCOPE, CollectionRun
from amayama_scraper.domain.collection_context import CollectionContext, build_scope


def test_default_scope_matches_the_fixed_constant():
    run = CollectionRun(run_id="run-1")
    assert run.scope == FIXED_SCOPE == "AMAYAMA:VOLKSWAGEN:AMAROK:AMA-BR"


def test_build_scope_for_default_amarok_params_matches_fixed_scope():
    """Requisito: default da CLI continua produzindo exatamente o escopo
    histórico da Amarok/AMA-BR — nenhuma mudança de comportamento default."""
    context = CollectionContext(manufacturer="VOLKSWAGEN", vehicle_model="AMAROK", market="AMA-BR")
    assert build_scope(context) == FIXED_SCOPE
    assert context.scope() == FIXED_SCOPE


def test_build_scope_for_another_model_differs_from_amarok():
    """Requisito: outro modelo gera um scope diferente do da Amarok."""
    other_context = CollectionContext(
        manufacturer="VOLKSWAGEN", vehicle_model="GOL", market="AMA-BR"
    )
    other_scope = build_scope(other_context)
    assert other_scope != FIXED_SCOPE
    assert other_scope == "AMAYAMA:VOLKSWAGEN:GOL:AMA-BR"


def test_build_scope_normalizes_case_and_whitespace():
    context = CollectionContext(
        manufacturer="volkswagen", vehicle_model=" gol ", market="ama-br"
    )
    assert build_scope(context) == "AMAYAMA:VOLKSWAGEN:GOL:AMA-BR"
