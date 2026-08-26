"""Política de freshness — Constitution §11.

Configuração (não constante rígida): diferencia specs atuais (em produção)
de specs encerradas — research.md §12 já usa a mesma distinção para
"catálogo mais atual". Um valor concreto é decisão operacional, não
semântica (contracts/equivalence-contracts.md "Revalidação incremental").
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True, slots=True)
class FreshnessPolicy:
    active_production_max_age: timedelta
    discontinued_production_max_age: timedelta

    def max_age_for(self, *, production_end: datetime | None) -> timedelta:
        """production_end is None => em produção (ativa); caso contrário, encerrada."""
        if production_end is None:
            return self.active_production_max_age
        return self.discontinued_production_max_age

    def is_candidate_for_revalidation(
        self, *, collected_at: datetime, now: datetime, production_end: datetime | None
    ) -> bool:
        max_age = self.max_age_for(production_end=production_end)
        return (now - collected_at) >= max_age


#: Valores operacionais de exemplo — nenhum indicador de "versão de catálogo" foi
#: fornecido pela fonte (research.md §12), então o contrato delega explicitamente
#: este número a "decisão operacional, não semântica". Reconfigurável livremente;
#: não é um requisito de produto.
DEFAULT_FRESHNESS_POLICY = FreshnessPolicy(
    active_production_max_age=timedelta(days=30),
    discontinued_production_max_age=timedelta(days=180),
)
