"""T048/T049 — should_attempt_this_pass(): REQUIRES_EXPLICIT_RETRY só entra na
passada do driver com --retry-rejected explícito (FR-020, DEC-006)."""

from __future__ import annotations

import pytest

from amayama_scraper.orchestration.retry_classification import (
    PendingUnitClassification,
    should_attempt_this_pass,
)


@pytest.mark.parametrize(
    "classification",
    [
        PendingUnitClassification.NOT_YET_ATTEMPTED,
        PendingUnitClassification.TRANSPORT_RETRY,
        PendingUnitClassification.CHALLENGE_PAUSED,
    ],
)
def test_default_auto_classifications_are_always_attempted(
    classification: PendingUnitClassification,
) -> None:
    assert should_attempt_this_pass(classification, retry_rejected=False) is True
    assert should_attempt_this_pass(classification, retry_rejected=True) is True


def test_requires_explicit_retry_excluded_by_default() -> None:
    assert (
        should_attempt_this_pass(
            PendingUnitClassification.REQUIRES_EXPLICIT_RETRY, retry_rejected=False
        )
        is False
    )


def test_requires_explicit_retry_included_with_flag() -> None:
    assert (
        should_attempt_this_pass(
            PendingUnitClassification.REQUIRES_EXPLICIT_RETRY, retry_rejected=True
        )
        is True
    )
