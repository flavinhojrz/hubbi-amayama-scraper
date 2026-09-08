"""rate_limiter.py — política adaptativa de concorrência efetiva (005, US3).

Funções puras, sem I/O (Constitution §6) — o mesmo padrão já usado por
`checkpoint/checkpoint_entry.py::transition()`: a regra de negócio vive aqui,
isolada e testável em memória; a persistência entre processos (necessária
porque workers são processos de SO distintos, contracts/worker-pool-contract.md
§0) vive em `persistence/repositories/rate_limiter_repo.py`, que apenas lê o
estado atual, aplica estas funções, e grava o resultado — nunca decide
política por conta própria.

Política (spec.md FR-060 a FR-065, deliberadamente simples e determinística
— "não invente heurística complexa"):
  - `effective_concurrency` nunca sai de `[1, config.max_concurrency]`.
  - Um challenge observado, quando o número de challenges dentro da janela
    configurada atinge o limiar configurado, decrementa em exatamente 1 e
    reinicia o relógio de estabilidade.
  - Um período estável (sem nenhum challenge) igual ou maior que
    `stability_seconds`, com `effective_concurrency < max_concurrency`,
    incrementa em exatamente 1 e reinicia o relógio de estabilidade — um
    passo por período estável, nunca um salto direto ao teto.
  - A degradação é sempre prospectiva (afeta apenas o próximo claim de spec,
    contracts/worker-pool-contract.md §3) — nunca preempta trabalho já em
    progresso.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class RateLimiterConfig:
    max_concurrency: int
    challenge_window_seconds: float
    challenge_threshold: int
    stability_seconds: float

    def __post_init__(self) -> None:
        if self.max_concurrency < 1:
            raise ValueError("RateLimiterConfig.max_concurrency must be >= 1")
        if self.challenge_window_seconds <= 0:
            raise ValueError("RateLimiterConfig.challenge_window_seconds must be > 0")
        if self.challenge_threshold < 1:
            raise ValueError("RateLimiterConfig.challenge_threshold must be >= 1")
        if self.stability_seconds <= 0:
            raise ValueError("RateLimiterConfig.stability_seconds must be > 0")


@dataclass(frozen=True, slots=True)
class RateLimiterState:
    effective_concurrency: int
    stable_since: datetime

    def __post_init__(self) -> None:
        if self.effective_concurrency < 1:
            raise ValueError("RateLimiterState.effective_concurrency must be >= 1")


def initial_state(config: RateLimiterConfig, *, started_at: datetime) -> RateLimiterState:
    """Estado inicial de um run novo — concorrência efetiva no teto configurado
    (spec.md FR-060: inicializado em `--workers`), relógio de estabilidade
    começando no início do run (nenhum challenge ainda observado)."""
    return RateLimiterState(effective_concurrency=config.max_concurrency, stable_since=started_at)


def on_challenge_observed(
    state: RateLimiterState,
    now: datetime,
    config: RateLimiterConfig,
    *,
    recent_challenge_count_in_window: int,
) -> RateLimiterState:
    """FR-063: decrementa em 1 (piso 1) quando `recent_challenge_count_in_window`
    (calculado pelo chamador sobre `challenge_event`, dentro de
    `config.challenge_window_seconds`) atinge `config.challenge_threshold`.

    Nunca decrementa mais de uma vez por chamada, mesmo que o limiar tenha
    sido ultrapassado por uma margem grande — um evento, no máximo um passo.
    """
    if recent_challenge_count_in_window < config.challenge_threshold:
        return state
    new_concurrency = max(1, state.effective_concurrency - 1)
    return RateLimiterState(effective_concurrency=new_concurrency, stable_since=now)


def on_stability_tick(
    state: RateLimiterState, now: datetime, config: RateLimiterConfig
) -> RateLimiterState:
    """FR-064: incrementa em 1 (teto `config.max_concurrency`) quando
    `now - state.stable_since >= config.stability_seconds`. Reinicia o
    relógio de estabilidade sempre que incrementa — recuperação gradual, um
    passo por período estável (nunca um salto direto ao teto)."""
    if state.effective_concurrency >= config.max_concurrency:
        return state
    elapsed = (now - state.stable_since).total_seconds()
    if elapsed < config.stability_seconds:
        return state
    return RateLimiterState(effective_concurrency=state.effective_concurrency + 1, stable_since=now)


__all__ = [
    "RateLimiterConfig",
    "RateLimiterState",
    "initial_state",
    "on_challenge_observed",
    "on_stability_tick",
]
