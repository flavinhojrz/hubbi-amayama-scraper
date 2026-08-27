"""Ports adicionais para finalize_spec_entry() — mesma inversão de dependência de
ingestion/ports.py (contracts/ports-contract.md), agora para manifest/checkpoint/
snapshot/fingerprint/current-state.

contracts/ports-contract.md fecha explicitamente `snapshots/` fora do escopo de
quem conhece adapters concretos de persistência ("a composição... acontece na
camada de orquestração/composição raiz, fora do escopo de ... snapshots/") —
`finalize_spec_entry()` (snapshots/finalize.py) por isso recebe estes ports por
injeção, nunca importa `persistence/`/`sqlite3` diretamente. A Phase 14
(orchestration/) instancia os adapters concretos (persistence/adapters/) que os
satisfazem.
"""

from __future__ import annotations

from typing import Protocol

from amayama_scraper.checkpoint.checkpoint_entry import CheckpointEntry
from amayama_scraper.domain.current_state import CurrentSpecState
from amayama_scraper.domain.manifest import SpecGroupManifest
from amayama_scraper.fingerprints.types import FingerprintSet
from amayama_scraper.snapshots.snapshot import SpecSnapshot


class ManifestRepository(Protocol):
    def get_authoritative(self, spec_key: str, run_id: str) -> SpecGroupManifest | None: ...


class CheckpointQueryRepository(Protocol):
    def list_accepted(self, run_id: str, spec_key: str) -> list[CheckpointEntry]: ...


class SnapshotRepository(Protocol):
    def save(self, snapshot: SpecSnapshot) -> str:
        """Insert-or-get por idempotency_key — retorna sempre o snapshot_id vigente."""
        ...

    def get_by_idempotency_key(self, idempotency_key: str) -> SpecSnapshot | None: ...

    def supersede(self, snapshot_id: str) -> None: ...


class FingerprintWriteRepository(Protocol):
    def update(self, snapshot_id: str, fingerprints: FingerprintSet) -> None: ...


class CurrentStateRepository(Protocol):
    def materialize(self, spec_identity_ref: str) -> CurrentSpecState | None: ...
