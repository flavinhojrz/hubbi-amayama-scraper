"""classify_pending_unit() — DEC-006, contracts/orchestration-contract.md §2.

Classificação de CONSUMO — não é um novo status persistido. Deriva
inteiramente de CheckpointEntry.status/evidence, já existentes de 001.
Nenhuma nova transição de estado foi necessária (REJECTED -> IN_PROGRESS
via START_ATTEMPT já era permitida — checkpoint/checkpoint_entry.py,
confirmado por tests/unit/test_checkpoint_transitions.py).
"""

from __future__ import annotations

from enum import StrEnum

from amayama_scraper.checkpoint.checkpoint_entry import CheckpointEntry, CheckpointStatus


class PendingUnitClassification(StrEnum):
    NOT_YET_ATTEMPTED = "NOT_YET_ATTEMPTED"
    TRANSPORT_RETRY = "TRANSPORT_RETRY"
    CHALLENGE_PAUSED = "CHALLENGE_PAUSED"
    REQUIRES_EXPLICIT_RETRY = "REQUIRES_EXPLICIT_RETRY"


def classify_pending_unit(entry: CheckpointEntry | None) -> PendingUnitClassification:
    if entry is None or entry.status is CheckpointStatus.PENDING:
        return PendingUnitClassification.NOT_YET_ATTEMPTED
    if entry.status is CheckpointStatus.IN_PROGRESS:
        return PendingUnitClassification.TRANSPORT_RETRY
    # status == REJECTED
    if entry.evidence.get("outcome") == "CHALLENGE":
        return PendingUnitClassification.CHALLENGE_PAUSED
    return PendingUnitClassification.REQUIRES_EXPLICIT_RETRY
    # covers: evidence["outcome"] in {INVALID, INCOMPLETE, TRANSLATION_CONTAMINATED}
    #         and "critical_error" in evidence (post-acceptance parsing failure)


#: Classificações tentadas automaticamente por padrão, sem ação explícita do
#: operador (contracts/orchestration-contract.md §2).
_DEFAULT_AUTO_CLASSIFICATIONS = frozenset(
    {
        PendingUnitClassification.NOT_YET_ATTEMPTED,
        PendingUnitClassification.TRANSPORT_RETRY,
        PendingUnitClassification.CHALLENGE_PAUSED,
    }
)


def should_attempt_this_pass(
    classification: PendingUnitClassification, *, retry_rejected: bool
) -> bool:
    """T048/T049 — filtro de inclusão por passada do driver (DEC-006).

    Por padrão, REQUIRES_EXPLICIT_RETRY nunca é incluída — só entra quando o
    operador passa `--retry-rejected` (ou filtro equivalente), emitindo
    START_ATTEMPT normalmente (transição já permitida pela máquina de
    estados existente, nenhuma operação nova de "reset" é necessária).
    """
    if classification in _DEFAULT_AUTO_CLASSIFICATIONS:
        return True
    return retry_rejected
