"""T219 — atomicidade de finalize_spec_entry(): falha na Fase 2 faz rollback completo
(sem snapshot órfão / current_spec_state inconsistente); falha na Fase 1 nunca abre a
transação de escrita — a finalização é re-tentável (data-model.md §13c)."""

import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from amayama_scraper.checkpoint.checkpoint_entry import CheckpointEvent
from amayama_scraper.checkpoint.collection_run import CollectionRun
from amayama_scraper.checkpoint.upsert import upsert_checkpoint
from amayama_scraper.domain.manifest import ManifestCategory, ManifestGroupRef, SpecGroupManifest
from amayama_scraper.ingestion.accept import accept_capture
from amayama_scraper.ingestion.capture_input import RawCaptureInput
from amayama_scraper.ingestion.capture_kind import CaptureKind
from amayama_scraper.persistence.adapters.filesystem_raw_blob_store import FilesystemRawBlobStore
from amayama_scraper.persistence.adapters.snapshot_adapters import (
    SqliteCheckpointQueryRepositoryAdapter,
    SqliteCurrentStateRepositoryAdapter,
    SqliteFingerprintWriteRepositoryAdapter,
    SqliteManifestRepositoryAdapter,
    SqliteSnapshotRepositoryAdapter,
)
from amayama_scraper.persistence.adapters.sqlite_raw_capture_repository import (
    SqliteRawCaptureRepository,
)
from amayama_scraper.persistence.db import connect, run_in_transaction
from amayama_scraper.persistence.migrations.runner import run_migrations
from amayama_scraper.persistence.repositories.checkpoint_repo import save_collection_run
from amayama_scraper.persistence.repositories.manifest_repo import save_manifest
from amayama_scraper.snapshots.finalize import finalize_spec_entry, plan_finalization

VALID_GROUP_HTML = """
<html><body><div class="epcVariation__details"><div class="epcSchema__schemas">
  <div class="epcSchema__schema" data-id="SCH-1"><table class="entriesTable">
    <tr data-key="A01"><td class="entriesTable__number">1K0407151</td>
    <td class="entriesTable__description">Control arm</td>
    <td class="entriesTable__period">08.2010-12.2015</td>
    <td class="entriesTable__required">1</td></tr>
  </table></div>
</div></div></body></html>
"""


def _setup(tmp_path: Path):
    conn = connect(str(tmp_path / "db.sqlite3"))
    run_migrations(conn)
    conn.execute(
        "INSERT INTO spec_registry (stable_key, source, manufacturer, vehicle_model, "
        "market, model_code, amayama_catalog_id, production_period_raw, source_url) "
        "VALUES ('spec-1', 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H')"
    )
    save_collection_run(conn, CollectionRun(run_id="run-1"))
    manifest = SpecGroupManifest(
        spec_key="spec-1",
        source_capture_id="cap-manifest",
        discovered_at=datetime(2026, 8, 26, tzinfo=UTC),
        categories=(
            ManifestCategory(
                category_slug="front-axle-steering",
                groups=(ManifestGroupRef(group_id="407", source_url="https://x/407"),),
            ),
        ),
        manifest_complete=True,
    )
    save_manifest(conn, manifest, run_id="run-1")
    blob_store = FilesystemRawBlobStore(tmp_path / "blobs", conn)
    capture_repo = SqliteRawCaptureRepository(conn)

    captured = accept_capture(
        RawCaptureInput(
            capture_kind=CaptureKind.GROUP_DETAIL,
            source_url="https://x/407",
            collected_at=datetime.now(UTC),
            raw_content=VALID_GROUP_HTML.encode("utf-8"),
            run_id="run-1",
        ),
        blob_store,
        capture_repo,
    )
    upsert_checkpoint(
        conn,
        run_id="run-1",
        spec_key="spec-1",
        category_slug="front-axle-steering",
        group_id="407",
        event=CheckpointEvent.START_ATTEMPT,
    )
    upsert_checkpoint(
        conn,
        run_id="run-1",
        spec_key="spec-1",
        category_slug="front-axle-steering",
        group_id="407",
        event=CheckpointEvent.ACCEPT,
        raw_capture_id=captured.capture_id,
    )
    return conn, blob_store, capture_repo


class _ExplodingSnapshotRepo:
    """Wraps a real adapter but raises on save() — simulates a Fase 2 failure."""

    def __init__(self, real):
        self._real = real

    def save(self, snapshot):
        raise RuntimeError("simulated Fase 2 write failure")

    def get_by_idempotency_key(self, idempotency_key: str):
        return self._real.get_by_idempotency_key(idempotency_key)

    def supersede(self, snapshot_id: str) -> None:
        self._real.supersede(snapshot_id)


def test_phase_2_failure_rolls_back_completely_no_orphan_state(tmp_path: Path):
    conn, blob_store, capture_repo = _setup(tmp_path)
    real_snapshot_repo = SqliteSnapshotRepositoryAdapter(conn)

    with pytest.raises(RuntimeError, match="simulated Fase 2"):
        finalize_spec_entry(
            spec_key="spec-1",
            run_id="run-1",
            spec_identity_ref="spec-1",
            manifest_repo=SqliteManifestRepositoryAdapter(conn),
            checkpoint_repo=SqliteCheckpointQueryRepositoryAdapter(conn),
            capture_repo=capture_repo,
            blob_store=blob_store,
            snapshot_repo=_ExplodingSnapshotRepo(real_snapshot_repo),
            fingerprint_repo=SqliteFingerprintWriteRepositoryAdapter(conn),
            current_state_repo=SqliteCurrentStateRepositoryAdapter(conn),
            run_in_transaction=lambda fn: run_in_transaction(conn, fn),
            snapshot_id_factory=lambda: str(uuid.uuid4()),
            now_factory=lambda: datetime.now(UTC),
        )

    # nothing persisted: no snapshot row, no current_spec_state row
    assert conn.execute("SELECT COUNT(*) AS c FROM spec_snapshot").fetchone()["c"] == 0
    assert conn.execute("SELECT COUNT(*) AS c FROM current_spec_state").fetchone()["c"] == 0


def test_phase_1_failure_never_opens_the_write_transaction_retriable(tmp_path: Path):
    conn, blob_store, capture_repo = _setup(tmp_path)

    class _BrokenBlobStore:
        def get_or_create(self, content_hash, raw_content):
            raise AssertionError

        def read(self, content_hash):
            raise FileNotFoundError("simulated missing RawBlob")

    with pytest.raises(FileNotFoundError):
        plan_finalization(
            spec_key="spec-1",
            run_id="run-1",
            spec_identity_ref="spec-1",
            manifest_repo=SqliteManifestRepositoryAdapter(conn),
            checkpoint_repo=SqliteCheckpointQueryRepositoryAdapter(conn),
            capture_repo=capture_repo,
            blob_store=_BrokenBlobStore(),
        )

    # Fase 1 never opens a write transaction — nothing persisted at all
    assert conn.execute("SELECT COUNT(*) AS c FROM spec_snapshot").fetchone()["c"] == 0

    # retriable: a fresh call with a working blob_store succeeds normally
    snapshot = finalize_spec_entry(
        spec_key="spec-1",
        run_id="run-1",
        spec_identity_ref="spec-1",
        manifest_repo=SqliteManifestRepositoryAdapter(conn),
        checkpoint_repo=SqliteCheckpointQueryRepositoryAdapter(conn),
        capture_repo=capture_repo,
        blob_store=blob_store,
        snapshot_repo=SqliteSnapshotRepositoryAdapter(conn),
        fingerprint_repo=SqliteFingerprintWriteRepositoryAdapter(conn),
        current_state_repo=SqliteCurrentStateRepositoryAdapter(conn),
        run_in_transaction=lambda fn: run_in_transaction(conn, fn),
        snapshot_id_factory=lambda: str(uuid.uuid4()),
        now_factory=lambda: datetime.now(UTC),
    )
    assert snapshot is not None
