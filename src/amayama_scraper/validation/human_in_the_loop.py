"""Roteamento human-in-the-loop para outcomes CHALLENGE (FR-011, Constitution §5).

Nunca tenta contornar o challenge — apenas sinaliza a necessidade de
intervenção humana. Challenge nunca é tratado como conteúdo vazio válido.
"""

from __future__ import annotations

from dataclasses import dataclass

from amayama_scraper.validation.types import CaptureValidationResult, ValidationOutcome


@dataclass(frozen=True, slots=True)
class HumanInTheLoopSignal:
    source_url: str
    evidence: dict[str, object]
    message: str = "Challenge detectado — intervenção humana necessária antes de prosseguir."


def route_if_challenge(
    source_url: str, validation_result: CaptureValidationResult
) -> HumanInTheLoopSignal | None:
    """Retorna um sinal de human-in-the-loop quando o outcome é CHALLENGE, senão None.

    Nunca retorna um sinal de "sucesso"/"conteúdo aceito" para um challenge —
    essa distinção é o que impede que challenge seja mascarado como página
    vazia válida (contracts/input-contracts.md §2).
    """
    if validation_result.primary_outcome is not ValidationOutcome.CHALLENGE:
        return None
    return HumanInTheLoopSignal(source_url=source_url, evidence=validation_result.evidence)
