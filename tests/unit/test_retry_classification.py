"""T042-T045 — classify_pending_unit() (DEC-006, contracts/orchestration-contract.md §2).

Função pura, síncrona, sem I/O — deriva inteiramente de CheckpointEntry.status/
evidence já existentes. Nenhum novo CheckpointStatus é criado.
"""

from __future__ import annotations

from amayama_scraper.checkpoint.checkpoint_entry import CheckpointEntry, CheckpointStatus
from amayama_scraper.orchestration.retry_classification import (
    PendingUnitClassification,
    classify_pending_unit,
)

_KWARGS = dict(run_id="run-1", spec_key="spec-1", category_slug="engine", group_id="1")


def _entry(**overrides: object) -> CheckpointEntry:
    defaults: dict[str, object] = dict(_KWARGS)
    defaults.update(overrides)
    return CheckpointEntry(**defaults)  # type: ignore[arg-type]


# T042 — ausente/PENDING


def test_none_entry_is_not_yet_attempted() -> None:
    assert classify_pending_unit(None) is PendingUnitClassification.NOT_YET_ATTEMPTED


def test_pending_entry_is_not_yet_attempted() -> None:
    entry = _entry(status=CheckpointStatus.PENDING)
    assert classify_pending_unit(entry) is PendingUnitClassification.NOT_YET_ATTEMPTED


# T043 — IN_PROGRESS órfã


def test_in_progress_entry_is_transport_retry() -> None:
    entry = _entry(status=CheckpointStatus.IN_PROGRESS, attempt_count=1)
    assert classify_pending_unit(entry) is PendingUnitClassification.TRANSPORT_RETRY


# T044 — REJECTED com outcome CHALLENGE


def test_rejected_with_challenge_outcome_is_challenge_paused() -> None:
    entry = _entry(status=CheckpointStatus.REJECTED, evidence={"outcome": "CHALLENGE"})
    assert classify_pending_unit(entry) is PendingUnitClassification.CHALLENGE_PAUSED


# T045 — REJECTED com INVALID/INCOMPLETE/TRANSLATION_CONTAMINATED/critical_error


def test_rejected_with_invalid_outcome_requires_explicit_retry() -> None:
    entry = _entry(status=CheckpointStatus.REJECTED, evidence={"outcome": "INVALID"})
    assert classify_pending_unit(entry) is PendingUnitClassification.REQUIRES_EXPLICIT_RETRY


def test_rejected_with_incomplete_outcome_requires_explicit_retry() -> None:
    entry = _entry(status=CheckpointStatus.REJECTED, evidence={"outcome": "INCOMPLETE"})
    assert classify_pending_unit(entry) is PendingUnitClassification.REQUIRES_EXPLICIT_RETRY


def test_rejected_with_translation_contaminated_outcome_requires_explicit_retry() -> None:
    entry = _entry(
        status=CheckpointStatus.REJECTED, evidence={"outcome": "TRANSLATION_CONTAMINATED"}
    )
    assert classify_pending_unit(entry) is PendingUnitClassification.REQUIRES_EXPLICIT_RETRY


def test_rejected_with_critical_error_requires_explicit_retry() -> None:
    entry = _entry(
        status=CheckpointStatus.REJECTED, evidence={"critical_error": "unexpected structure"}
    )
    assert classify_pending_unit(entry) is PendingUnitClassification.REQUIRES_EXPLICIT_RETRY
