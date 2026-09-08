"""T236/T237 — run_collection() coordena múltiplas capturas sob o mesmo CollectionRun
e try_finalize_spec_entry() finaliza automaticamente quando o manifesto é totalmente
coberto (data-model.md §17)."""

from datetime import UTC, datetime
from pathlib import Path

from tests.support import AMAROK_CONTEXT

from amayama_scraper.checkpoint.collection_run import CollectionRun
from amayama_scraper.ingestion.capture_input import RawCaptureInput
from amayama_scraper.ingestion.capture_kind import CaptureKind
from amayama_scraper.orchestration.pipeline import CollectionInput, run_collection
from amayama_scraper.persistence.adapters.filesystem_raw_blob_store import FilesystemRawBlobStore
from amayama_scraper.persistence.adapters.sqlite_raw_capture_repository import (
    SqliteRawCaptureRepository,
)
from amayama_scraper.persistence.db import connect
from amayama_scraper.persistence.migrations.runner import run_migrations
from amayama_scraper.persistence.repositories.checkpoint_repo import save_collection_run
from amayama_scraper.persistence.repositories.current_state_repo import get_current_state
from amayama_scraper.snapshots.snapshot import SnapshotState

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

GROUP_HTML = """
<html><body><div class="epcVariation__details"><div class="epcSchema__schemas">
  <div class="epcSchema__schema" data-id="SCH-1"><table class="entriesTable">
    <tr data-key="A01"><td class="entriesTable__number">1K0407151</td>
    <td class="entriesTable__description">Control arm</td>
    <td class="entriesTable__period">08.2010-12.2015</td>
    <td class="entriesTable__required">1</td></tr>
  </table></div>
</div></div></body></html>
"""


def test_full_manifest_plus_group_detail_auto_finalizes(tmp_path: Path):
    conn = connect(str(tmp_path / "db.sqlite3"))
    run_migrations(conn)
    # source/manufacturer/vehicle_model/market precisam bater com
    # AMAROK_CONTEXT (004: process_capture()/try_finalize_spec_entry()
    # validam spec_key -> context antes de qualquer persistência).
    conn.execute(
        "INSERT INTO spec_registry (stable_key, source, manufacturer, vehicle_model, "
        "market, model_code, amayama_catalog_id, production_period_raw, source_url) "
        "VALUES ('spec-1', 'AMAYAMA', 'VOLKSWAGEN', 'AMAROK', 'AMA-BR', 'E', 'F', 'G', 'H')"
    )
    save_collection_run(conn, CollectionRun(run_id="run-1"))
    blob_store = FilesystemRawBlobStore(tmp_path / "blobs", conn)
    capture_repo = SqliteRawCaptureRepository(conn)

    # a manifest with a single expected group, so accepting that one group
    # completes the collection immediately.
    manifest_html = """
    <html><body>
      <div class="epcVariation__details">
        <div class="epcVariation__filters">
          <div class="epcVariation__schemaGroups">
            <a class="epcVariation__schemaGroup active" data-id="" href="https://x#">All</a>
            <a class="epcVariation__schemaGroup" data-id="4" href="https://x/front-axle-steering">FA</a>
          </div>
        </div>
        <div class="epcVariation__schemas">
          <div class="epcVariation__schema" data-id="407">
            <div class="epcVariation__schema-name">
              <a href="https://x/front-axle-steering/407">407</a>
            </div>
          </div>
        </div>
      </div>
    </body></html>
    """

    captures = [
        CollectionInput(
            capture_input=RawCaptureInput(
                capture_kind=CaptureKind.SPEC_NAVIGATION,
                source_url="https://x/spec-1",
                collected_at=datetime.now(UTC),
                raw_content=manifest_html.encode("utf-8"),
                run_id="run-1",
            ),
            spec_key="spec-1",
        ),
        CollectionInput(
            capture_input=RawCaptureInput(
                capture_kind=CaptureKind.GROUP_DETAIL,
                source_url="https://x/front-axle-steering/407",
                collected_at=datetime.now(UTC),
                raw_content=GROUP_HTML.encode("utf-8"),
                run_id="run-1",
            ),
            category_slug="front-axle-steering",
            group_id="407",
            spec_key="spec-1",
        ),
    ]

    results = run_collection(
        conn, blob_store, capture_repo, "run-1", captures, context=AMAROK_CONTEXT
    )
    assert len(results) == 2
    assert all(r.routed_to_parser for r in results)

    current = get_current_state(conn, "spec-1")
    assert current is not None
    snapshot_row = conn.execute(
        "SELECT state FROM spec_snapshot WHERE snapshot_id = ?", (current.latest_snapshot_id,)
    ).fetchone()
    assert snapshot_row["state"] == SnapshotState.VALID.value
