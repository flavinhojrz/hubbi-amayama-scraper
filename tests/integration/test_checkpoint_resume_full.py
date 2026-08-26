"""T251 — checkpoint/resume hierárquico completo, incluindo Cenário E — restart real
de processo: manifesto autoritativo persistido; Group A e Group B aceitos; TODA
representação em memória descartada; novos repositórios/serviços instanciados
(simulando um processo novo); finalize_spec_entry() a partir dessa nova instância
reconstrói exclusivamente via manifest_repo/checkpoint_repo/capture_repo/blob_store/
parse_group_detail() — nenhum dos dois grupos é recoletado, snapshot resultante VALID
(quickstart.md Cenário 9; data-model.md §13c)."""

import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from amayama_scraper.checkpoint.checkpoint_entry import CheckpointEvent
from amayama_scraper.checkpoint.collection_run import CollectionRun
from amayama_scraper.checkpoint.resume import NoAuthoritativeManifestError, get_pending_groups
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
from amayama_scraper.snapshots.finalize import finalize_spec_entry
from amayama_scraper.snapshots.snapshot import SnapshotState

GROUP_A_HTML = """
<html><body><div class="epcVariation__details"><div class="epcSchema__schemas">
  <div class="epcSchema__schema" data-id="SCH-A"><table class="entriesTable">
    <tr data-key="A01"><td class="entriesTable__number">1K0407151</td>
    <td class="entriesTable__description">Control arm</td>
    <td class="entriesTable__period">08.2010-12.2015</td>
    <td class="entriesTable__required">1</td></tr>
  </table></div>
</div></div></body></html>
"""

GROUP_B_HTML = """
<html><body><div class="epcVariation__details"><div class="epcSchema__schemas">
  <div class="epcSchema__schema" data-id="SCH-B"><table class="entriesTable">
    <tr data-key="B01"><td class="entriesTable__number">1K0409001</td>
    <td class="entriesTable__description">Final drive housing</td>
    <td class="entriesTable__period">08.2010-12.2015</td>
    <td class="entriesTable__required">1</td></tr>
  </table></div>
</div></div></body></html>
"""


def test_cenario_a_no_authoritative_manifest_pending_lookup_raises(tmp_path: Path):
    conn = connect(str(tmp_path / "db.sqlite3"))
    run_migrations(conn)
    save_collection_run(conn, CollectionRun(run_id="run-1"))
    with pytest.raises(NoAuthoritativeManifestError):
        get_pending_groups(conn, "run-1", "spec-unknown")


def test_cenario_e_full_process_restart_before_finalization(tmp_path: Path):
    db_path = str(tmp_path / "db.sqlite3")
    blobs_path = tmp_path / "blobs"

    # --- "process 1": collect the manifest and accept both groups ---
    conn1 = connect(db_path)
    run_migrations(conn1)
    conn1.execute(
        "INSERT INTO spec_registry (stable_key, source, manufacturer, vehicle_model, "
        "market, model_code, amayama_catalog_id, production_period_raw, source_url) "
        "VALUES ('spec-1', 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H')"
    )
    save_collection_run(conn1, CollectionRun(run_id="run-1"))
    manifest = SpecGroupManifest(
        spec_key="spec-1",
        source_capture_id="cap-manifest",
        discovered_at=datetime(2026, 8, 26, tzinfo=UTC),
        categories=(
            ManifestCategory(
                category_slug="front-axle-steering",
                groups=(
                    ManifestGroupRef(group_id="407", source_url="https://x/407"),
                    ManifestGroupRef(group_id="409", source_url="https://x/409"),
                ),
            ),
        ),
        manifest_complete=True,
    )
    save_manifest(conn1, manifest, run_id="run-1")

    blob_store1 = FilesystemRawBlobStore(blobs_path, conn1)
    capture_repo1 = SqliteRawCaptureRepository(conn1)

    captured_ids = {}
    for group_id, html in (("407", GROUP_A_HTML), ("409", GROUP_B_HTML)):
        captured = accept_capture(
            RawCaptureInput(
                capture_kind=CaptureKind.GROUP_DETAIL,
                source_url=f"https://x/{group_id}",
                collected_at=datetime.now(UTC),
                raw_content=html.encode("utf-8"),
                run_id="run-1",
            ),
            blob_store1,
            capture_repo1,
        )
        captured_ids[group_id] = captured.capture_id
        upsert_checkpoint(
            conn1,
            run_id="run-1",
            spec_key="spec-1",
            category_slug="front-axle-steering",
            group_id=group_id,
            event=CheckpointEvent.START_ATTEMPT,
        )
        upsert_checkpoint(
            conn1,
            run_id="run-1",
            spec_key="spec-1",
            category_slug="front-axle-steering",
            group_id=group_id,
            event=CheckpointEvent.ACCEPT,
            raw_capture_id=captured.capture_id,
        )

    # --- discard EVERYTHING in-memory from "process 1": no ParsedGroupDetail,
    #     no tree, no manifest object, no repo instances survive ---
    del conn1, blob_store1, capture_repo1, manifest

    # --- "process 2": brand-new connection + brand-new adapter instances,
    #     simulating a full restart ---
    conn2 = connect(db_path)
    blob_store2 = FilesystemRawBlobStore(blobs_path, conn2)
    capture_repo2 = SqliteRawCaptureRepository(conn2)

    pending = get_pending_groups(conn2, "run-1", "spec-1")
    assert pending == []  # both groups already ACCEPTED — nothing left to (re)collect

    snapshot = finalize_spec_entry(
        spec_key="spec-1",
        run_id="run-1",
        spec_identity_ref="spec-1",
        manifest_repo=SqliteManifestRepositoryAdapter(conn2),
        checkpoint_repo=SqliteCheckpointQueryRepositoryAdapter(conn2),
        capture_repo=capture_repo2,
        blob_store=blob_store2,
        snapshot_repo=SqliteSnapshotRepositoryAdapter(conn2),
        fingerprint_repo=SqliteFingerprintWriteRepositoryAdapter(conn2),
        current_state_repo=SqliteCurrentStateRepositoryAdapter(conn2),
        run_in_transaction=lambda fn: run_in_transaction(conn2, fn),
        snapshot_id_factory=lambda: str(uuid.uuid4()),
        now_factory=lambda: datetime.now(UTC),
    )

    assert snapshot is not None
    assert snapshot.state == SnapshotState.VALID
    assert snapshot.collection_complete is True

    # no group was "recollected" — the raw_capture rows are exactly the ones
    # accepted by "process 1", reconstructed via capture_repo.get()+blob_store.read()
    row_count = conn2.execute("SELECT COUNT(*) AS c FROM raw_capture").fetchone()["c"]
    assert row_count == 2
