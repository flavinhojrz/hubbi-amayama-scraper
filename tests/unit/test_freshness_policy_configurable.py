"""T232 — política de freshness é configurável e pode diferenciar specs
atuais vs. encerradas (Constitution §11)."""

from datetime import UTC, datetime, timedelta

from amayama_scraper.snapshots.freshness_policy import DEFAULT_FRESHNESS_POLICY, FreshnessPolicy


def test_active_and_discontinued_use_different_max_age():
    policy = FreshnessPolicy(
        active_production_max_age=timedelta(days=10),
        discontinued_production_max_age=timedelta(days=100),
    )
    assert policy.max_age_for(production_end=None) == timedelta(days=10)
    assert policy.max_age_for(production_end=datetime(2020, 1, 1, tzinfo=UTC)) == timedelta(
        days=100
    )


def test_policy_is_fully_configurable_not_a_rigid_constant():
    custom = FreshnessPolicy(
        active_production_max_age=timedelta(hours=1),
        discontinued_production_max_age=timedelta(days=365),
    )
    assert custom != DEFAULT_FRESHNESS_POLICY
    assert custom.active_production_max_age == timedelta(hours=1)


def test_is_candidate_for_revalidation_respects_configured_age():
    policy = FreshnessPolicy(
        active_production_max_age=timedelta(days=10),
        discontinued_production_max_age=timedelta(days=100),
    )
    now = datetime(2026, 1, 20, tzinfo=UTC)

    fresh = policy.is_candidate_for_revalidation(
        collected_at=datetime(2026, 1, 15, tzinfo=UTC), now=now, production_end=None
    )
    stale = policy.is_candidate_for_revalidation(
        collected_at=datetime(2026, 1, 1, tzinfo=UTC), now=now, production_end=None
    )
    assert fresh is False
    assert stale is True
