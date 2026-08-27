"""T220 — duas RawCapture com mesmo content_hash em runs/momentos diferentes
preservam provenance distinto e não colapsam a finalização (data-model.md §4b/§13b)."""

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
from amayama_scraper.persistence.repositories.manifest_repo import save_manifest
from amayama_scraper.snapshots.finalize import finalize_spec_entry

SAME_GROUP_HTML = """
<html><body><div class="epcVariation__details"><div class="epcSchema__schemas">
  <div class="epcSchema__schema" data-id="SCH-1"><table class="entriesTable">
    <tr data-key="A01"><td class="entriesTable__number">1K0407151</td>
    <td class="entriesTable__description">Control arm</td>
    <td class="entriesTable__period">08.2010-12.2015</td>
    <td class="entriesTable__required">1</td></tr>
  </table></div>
</div></div></body></html>
"""


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


def test_identical_content_recollected_in_a_new_run_is_a_distinct_observation_but_same_snapshot(
    tmp_path: Path,
):
    conn = connect(str(tmp_path / "db.sqlite3"))
    run_migrations(conn)
    conn.execute(
        "INSERT INTO spec_registry (stable_key, source, manufacturer, vehicle_model, "
        "market, model_code, amayama_catalog_id, production_period_raw, source_url) "
        "VALUES ('spec-1', 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H')"
    )
    blob_store = FilesystemRawBlobStore(tmp_path / "blobs", conn)
    capture_repo = SqliteRawCaptureRepository(conn)

    capture_ids = []
    for run_id in ("run-1", "run-2"):
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
                raw_content=SAME_GROUP_HTML.encode("utf-8"),  # byte-identical both times
                run_id=run_id,
            ),
            blob_store,
            capture_repo,
        )
        capture_ids.append(captured.capture_id)
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

    # two distinct RawCapture observations, same physical content_hash
    assert capture_ids[0] != capture_ids[1]
    blob_count = conn.execute("SELECT COUNT(*) AS c FROM raw_blob").fetchone()["c"]
    assert blob_count == 1  # deduplicated physically
    capture_count = conn.execute("SELECT COUNT(*) AS c FROM raw_capture").fetchone()["c"]
    assert capture_count == 2  # never collapsed as observations

    first = _finalize(conn, blob_store, capture_repo, "run-1")
    second = _finalize(conn, blob_store, capture_repo, "run-2")

    assert first is not None
    assert second is not None
    # different runs -> different idempotency_key (new observation) -> distinct snapshots,
    # even though the underlying parsed content is byte-identical
    assert first.snapshot_id != second.snapshot_id
    assert first.spec_parts_hash == second.spec_parts_hash  # same content, though
