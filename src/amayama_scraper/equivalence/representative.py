"""select_representative() — Constitution §9, research.md §12.

Interpretação documentada (composição das métricas já fechadas em
research.md §12, sem inventar nenhuma nova): os 5 critérios operam sobre
um `RepresentativeCandidate` — um resumo leve por spec/snapshot (contagem
de imagens próprias, `collected_at`, proporção de completude de metadados,
`stable_key`) em vez do `SpecSnapshot` de persistência (que só guarda
hashes, não os dados necessários para medir cobertura/completude
diretamente) — decisão de forma de dado, não de critério.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from amayama_scraper.snapshots.snapshot import SnapshotState


class NoValidCandidateError(ValueError):
    """Nenhum candidato tem snapshot.state == VALID — não há representante possível."""


@dataclass(frozen=True, slots=True)
class RepresentativeCandidate:
    spec_identity_ref: str
    stable_key: str
    snapshot_state: SnapshotState
    own_image_count: int
    collected_at: datetime
    metadata_completeness_ratio: float


def _criterion_1_valid_snapshot(
    candidates: tuple[RepresentativeCandidate, ...],
) -> tuple[RepresentativeCandidate, ...]:
    return tuple(c for c in candidates if c.snapshot_state is SnapshotState.VALID)


def select_representative(candidates: tuple[RepresentativeCandidate, ...]) -> str:
    eligible = _criterion_1_valid_snapshot(candidates)
    if not eligible:
        raise NoValidCandidateError("no candidate has snapshot.state == VALID")

    winner = min(
        eligible,
        key=lambda c: (
            -c.own_image_count,  # criterion 2: maior cobertura de imagens próprias
            -c.collected_at.timestamp(),  # criterion 3: catálogo mais atual
            -c.metadata_completeness_ratio,  # criterion 4: maior completude
            c.stable_key,  # criterion 5: desempate lexicográfico
        ),
    )
    return winner.spec_identity_ref
