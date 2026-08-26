"""Adapters SQLite que satisfazem os ports de snapshots/ports.py.

Instanciados apenas na camada de orquestração/composição raiz
(contracts/ports-contract.md) — `snapshots/finalize.py` nunca conhece
estas classes nem `sqlite3` diretamente.
"""

from __future__ import annotations

import sqlite3

from amayama_scraper.checkpoint.checkpoint_entry import CheckpointEntry
from amayama_scraper.domain.current_state import CurrentSpecState
from amayama_scraper.domain.manifest import SpecGroupManifest
from amayama_scraper.fingerprints.types import FingerprintSet
from amayama_scraper.persistence.repositories import (
    checkpoint_repo,
    current_state_repo,
    fingerprint_repo,
    manifest_repo,
    snapshot_repo,
)
from amayama_scraper.snapshots.snapshot import SpecSnapshot


class SqliteManifestRepositoryAdapter:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get_authoritative(self, spec_key: str, run_id: str) -> SpecGroupManifest | None:
        return manifest_repo.get_authoritative(self._conn, spec_key, run_id)


class SqliteCheckpointQueryRepositoryAdapter:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def list_accepted(self, run_id: str, spec_key: str) -> list[CheckpointEntry]:
        return checkpoint_repo.list_accepted(self._conn, run_id, spec_key)


class SqliteSnapshotRepositoryAdapter:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def save(self, snapshot: SpecSnapshot) -> str:
        return snapshot_repo.save_snapshot(self._conn, snapshot)

    def get_by_idempotency_key(self, idempotency_key: str) -> SpecSnapshot | None:
        return snapshot_repo.get_by_idempotency_key(self._conn, idempotency_key)

    def supersede(self, snapshot_id: str) -> None:
        snapshot_repo.supersede(self._conn, snapshot_id)


class SqliteFingerprintWriteRepositoryAdapter:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def update(self, snapshot_id: str, fingerprints: FingerprintSet) -> None:
        fingerprint_repo.update_fingerprint_set(self._conn, snapshot_id, fingerprints)


class SqliteCurrentStateRepositoryAdapter:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def materialize(self, spec_identity_ref: str) -> CurrentSpecState | None:
        return current_state_repo.materialize(self._conn, spec_identity_ref)
