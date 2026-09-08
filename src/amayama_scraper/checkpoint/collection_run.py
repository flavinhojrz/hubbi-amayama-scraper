"""CollectionRun — escopo da execução de coleta (data-model.md §11).

Desde a evolução multi-modelo (002 -> 004), `scope` é a serialização
determinística de um `CollectionContext` (domain/collection_context.py) —
nunca mais um literal único fixo em código, e nunca mais validado por uma
igualdade contra um valor fixo: `__post_init__` agora exige que `scope`
decomponha (`parse_scope()`) em um `CollectionContext` válido, o que
generaliza a validação anterior sem enfraquecê-la (qualquer scope aceito
antes por igualdade com `FIXED_SCOPE` continua sendo aceito, pois já
satisfazia esse formato).

`FIXED_SCOPE` é mantido apenas como o valor *default* histórico (Amarok/
AMA-BR) de `CollectionRun.scope` — preserva compatibilidade para os
chamadores/testes que constroem `CollectionRun(run_id=...)` sem passar
`scope` explicitamente. É **legado/default apenas**: nenhuma lógica
operacional nova (cli/main.py, orchestration/) depende dele como fonte do
contexto corrente — o contexto corrente é sempre um `CollectionContext`
explícito, validado contra o `CollectionRun.scope` real (ver
orchestration/pipeline.py::process_capture, orchestration/collection_driver.py
::run_collection_driver).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from amayama_scraper.domain.collection_context import CollectionContext, parse_scope

#: Escopo default histórico (Constitution §2) — Amarok/AMA-BR. Legado: ver
#: docstring do módulo. Não é mais o único scope válido.
FIXED_SCOPE = "AMAYAMA:VOLKSWAGEN:AMAROK:AMA-BR"


@dataclass(frozen=True, slots=True)
class CollectionRun:
    run_id: str
    scope: str = FIXED_SCOPE
    started_at: datetime | None = None
    resumed_at: datetime | None = None
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.run_id or not self.run_id.strip():
            raise ValueError("CollectionRun.run_id must not be empty")
        # parse_scope() valida estrutura (4 componentes, alfabeto canônico,
        # nenhum vazio) — levanta ValueError (InvalidScopeError/
        # InvalidScopeComponentError, ambas subclasses de ValueError) para
        # qualquer scope malformado, incluindo o caso "" já coberto antes.
        parse_scope(self.scope)

    def context(self) -> CollectionContext:
        """Recupera o CollectionContext canônico deste run — único caminho
        oficial para "derivar o contexto operacional a partir do
        CollectionRun.scope" (004, item 1)."""
        return parse_scope(self.scope)
