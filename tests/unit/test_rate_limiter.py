"""T503 — orchestration/rate_limiter.py, funções puras (FR-060 a FR-065, SC-004)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from amayama_scraper.orchestration.rate_limiter import (
    RateLimiterConfig,
    RateLimiterState,
    initial_state,
    on_challenge_observed,
    on_stability_tick,
)

_T0 = datetime(2026, 9, 3, 12, 0, 0, tzinfo=UTC)


def _config(**overrides: object) -> RateLimiterConfig:
    defaults: dict[str, object] = {
        "max_concurrency": 4,
        "challenge_window_seconds": 300.0,
        "challenge_threshold": 1,
        "stability_seconds": 600.0,
    }
    defaults.update(overrides)
    return RateLimiterConfig(**defaults)  # type: ignore[arg-type]


def test_initial_state_starts_at_max_concurrency() -> None:
    config = _config(max_concurrency=3)
    state = initial_state(config, started_at=_T0)
    assert state.effective_concurrency == 3
    assert state.stable_since == _T0


def test_challenge_below_threshold_never_decrements() -> None:
    config = _config(challenge_threshold=3)
    state = RateLimiterState(effective_concurrency=4, stable_since=_T0)
    result = on_challenge_observed(
        state, _T0 + timedelta(seconds=10), config, recent_challenge_count_in_window=2
    )
    assert result == state


def test_challenge_at_threshold_decrements_by_exactly_one_and_resets_clock() -> None:
    config = _config(challenge_threshold=1)
    state = RateLimiterState(effective_concurrency=4, stable_since=_T0)
    now = _T0 + timedelta(seconds=10)
    result = on_challenge_observed(state, now, config, recent_challenge_count_in_window=1)
    assert result.effective_concurrency == 3
    assert result.stable_since == now


def test_challenge_never_decrements_below_one() -> None:
    config = _config(challenge_threshold=1)
    state = RateLimiterState(effective_concurrency=1, stable_since=_T0)
    result = on_challenge_observed(
        state, _T0 + timedelta(seconds=10), config, recent_challenge_count_in_window=5
    )
    assert result.effective_concurrency == 1


def test_challenge_decrements_by_at_most_one_even_with_large_overshoot() -> None:
    config = _config(challenge_threshold=1)
    state = RateLimiterState(effective_concurrency=4, stable_since=_T0)
    result = on_challenge_observed(
        state, _T0 + timedelta(seconds=10), config, recent_challenge_count_in_window=50
    )
    assert result.effective_concurrency == 3


def test_stability_tick_before_window_elapses_never_increments() -> None:
    config = _config(max_concurrency=4, stability_seconds=600.0)
    state = RateLimiterState(effective_concurrency=2, stable_since=_T0)
    result = on_stability_tick(state, _T0 + timedelta(seconds=599), config)
    assert result == state


def test_stability_tick_after_window_elapses_increments_by_exactly_one_and_resets_clock() -> None:
    config = _config(max_concurrency=4, stability_seconds=600.0)
    state = RateLimiterState(effective_concurrency=2, stable_since=_T0)
    now = _T0 + timedelta(seconds=600)
    result = on_stability_tick(state, now, config)
    assert result.effective_concurrency == 3
    assert result.stable_since == now


def test_stability_tick_never_exceeds_max_concurrency() -> None:
    config = _config(max_concurrency=4, stability_seconds=600.0)
    state = RateLimiterState(effective_concurrency=4, stable_since=_T0)
    result = on_stability_tick(state, _T0 + timedelta(days=1), config)
    assert result.effective_concurrency == 4
    assert result.stable_since == _T0  # already at ceiling — clock is not touched


def test_recovery_is_gradual_one_step_per_stable_period() -> None:
    """Long idle period increments one step at a time, never jumps to the ceiling."""
    config = _config(max_concurrency=4, stability_seconds=600.0)
    state = RateLimiterState(effective_concurrency=1, stable_since=_T0)
    now = _T0
    for expected in (2, 3, 4):
        now = now + timedelta(seconds=600)
        state = on_stability_tick(state, now, config)
        assert state.effective_concurrency == expected
    # a further stable tick, already at ceiling, is a no-op
    state = on_stability_tick(state, now + timedelta(seconds=600), config)
    assert state.effective_concurrency == 4


def test_deterministic_sequence_same_events_same_states() -> None:
    """SC-004: same event sequence (with injected clock) always produces the
    same state sequence — no dependency on wall-clock/randomness."""
    config = _config(max_concurrency=4, challenge_threshold=1, stability_seconds=600.0)

    def run() -> list[int]:
        state = initial_state(config, started_at=_T0)
        trace = [state.effective_concurrency]
        state = on_challenge_observed(
            state, _T0 + timedelta(seconds=5), config, recent_challenge_count_in_window=1
        )
        trace.append(state.effective_concurrency)
        state = on_challenge_observed(
            state, _T0 + timedelta(seconds=15), config, recent_challenge_count_in_window=1
        )
        trace.append(state.effective_concurrency)
        state = on_stability_tick(state, _T0 + timedelta(seconds=615), config)
        trace.append(state.effective_concurrency)
        return trace

    assert run() == run() == [4, 3, 2, 3]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_concurrency": 0},
        {"challenge_window_seconds": 0},
        {"challenge_threshold": 0},
        {"stability_seconds": 0},
    ],
)
def test_config_rejects_invalid_values(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        _config(**kwargs)


def test_state_rejects_concurrency_below_one() -> None:
    with pytest.raises(ValueError):
        RateLimiterState(effective_concurrency=0, stable_since=_T0)
