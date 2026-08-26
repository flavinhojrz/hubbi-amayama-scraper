"""T226 — falha de nova coleta não apaga/transiciona o último VALID conhecido
(FR-029, ponto 17 do PLAN)."""

import uuid
from datetime import UTC, datetime
from pathlib import Path

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
from amayama_scraper.persistence.repositories.current_state_repo import get_current_state
from amayama_scraper.persistence.repositories.manifest_repo import save_manifest
from amayama_scraper.persistence.repositories.snapshot_repo import get_snapshot
from amayama_scraper.snapshots.finalize import finalize_spec_entry
from amayama_scraper.snapshots.snapshot import SnapshotState

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

# missing the expected .epcSchema__schemas container -> critical_error on parse
DRIFTED_GROUP_HTML = """
<html><body><div class="epcVariation__details">
  <p>unexpected page layout</p>
</div></body></html>
"""


def _accept_group(conn, blob_store, capture_repo, html: str, run_id: str):
    save_collection_run(conn, CollectionRun(run_id=run_id))
    manifest = SpecGroupManifest(
        spec_key="spec-1",
        source_capture_id=f"cap-manifest-{run_id}",
        discovered_at=datetime(2026, 8, 26, tzinfo=UTC),
        categories=(
            ManifestCategory(
                category_slug="front-axle-steering",
                groups=(ManifestGroupRef(group_id="407", source_url="https://x/407"),),
            ),
        ),
        manifest_complete=True,
    )
    save_manifest(conn, manifest, run_id=run_id)

    captured = accept_capture(
        RawCaptureInput(
            capture_kind=CaptureKind.GROUP_DETAIL,
            source_url="https://x/407",
            collected_at=datetime.now(UTC),
            raw_content=html.encode("utf-8"),
            run_id=run_id,
        ),
        blob_store,
        capture_repo,
    )
    upsert_checkpoint(
        conn,
        run_id=run_id,
        spec_key="spec-1",
        category_slug="front-axle-steering",
        group_id="407",
        event=CheckpointEvent.START_ATTEMPT,
    )
    upsert_checkpoint(
        conn,
        run_id=run_id,
        spec_key="spec-1",
        category_slug="front-axle-steering",
        group_id="407",
        event=CheckpointEvent.ACCEPT,
        raw_capture_id=captured.capture_id,
    )


def _finalize(conn, blob_store, capture_repo, run_id: str):
    return finalize_spec_entry(
        spec_key="spec-1",
        run_id=run_id,
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


def test_invalid_new_snapshot_never_supersedes_last_known_good(tmp_path: Path):
    conn = connect(str(tmp_path / "db.sqlite3"))
    run_migrations(conn)
    conn.execute(
        "INSERT INTO spec_registry (stable_key, source, manufacturer, vehicle_model, "
        "market, model_code, amayama_catalog_id, production_period_raw, source_url) "
        "VALUES ('spec-1', 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H')"
    )
    blob_store = FilesystemRawBlobStore(tmp_path / "blobs", conn)
    capture_repo = SqliteRawCaptureRepository(conn)

    _accept_group(conn, blob_store, capture_repo, VALID_GROUP_HTML, run_id="run-1")
    good = _finalize(conn, blob_store, capture_repo, run_id="run-1")
    assert good is not None
    assert good.state == SnapshotState.VALID

    _accept_group(conn, blob_store, capture_repo, DRIFTED_GROUP_HTML, run_id="run-2")
    bad = _finalize(conn, blob_store, capture_repo, run_id="run-2")
    assert bad is not None
    assert bad.state == SnapshotState.INVALID

    # the good snapshot is untouched — still VALID, never SUPERSEDED
    reloaded_good = get_snapshot(conn, good.snapshot_id)
    assert reloaded_good is not None
    assert reloaded_good.state == SnapshotState.VALID

    # current_spec_state still points at the last KNOWN GOOD, not the failed attempt
    current = get_current_state(conn, "spec-1")
    assert current is not None
    assert current.latest_snapshot_id == good.snapshot_id
