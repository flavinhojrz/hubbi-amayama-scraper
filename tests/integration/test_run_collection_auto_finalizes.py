"""T236/T237 — run_collection_driver() coordena múltiplas capturas sob o mesmo
CollectionRun e try_finalize_spec_entry() finaliza automaticamente quando o
manifesto é totalmente coberto (data-model.md §17).

Bug fix (manifest truncado): a montagem do manifesto autoritativo
(`manifest_complete=True`) só acontece em
`orchestration/collection_driver.py::discover_spec_manifest()` — nunca em
`process_capture()`/`run_collection()` isolados (essas rotas persistem
apenas fragmentos de UMA página, nunca autoritativos sozinhos, ver
parsing/spec_group_manifest.py). Por isso este teste dirige o pipeline via
`run_collection_driver()` + `FakeBrowserTransport` (visita a categoria
declarada na sua própria URL antes do grupo), em vez de injetar
`CollectionInput`s de SPEC_NAVIGATION/GROUP_DETAIL diretamente via
`run_collection()`."""

from datetime import UTC, datetime
from pathlib import Path

from tests.support import AMAROK_CONTEXT
from tests.unit.fakes import FakeBrowserTransport

from amayama_scraper.checkpoint.collection_run import CollectionRun
from amayama_scraper.domain.identity import SpecIdentity
from amayama_scraper.orchestration.collection_driver import (
    OperationalFilters,
    run_collection_driver,
)
from amayama_scraper.persistence.adapters.filesystem_raw_blob_store import FilesystemRawBlobStore
from amayama_scraper.persistence.adapters.sqlite_raw_capture_repository import (
    SqliteRawCaptureRepository,
)
from amayama_scraper.persistence.db import connect
from amayama_scraper.persistence.migrations.runner import run_migrations
from amayama_scraper.persistence.repositories.checkpoint_repo import save_collection_run
from amayama_scraper.persistence.repositories.current_state_repo import get_current_state
from amayama_scraper.persistence.repositories.spec_registry_repo import save_spec_identity
from amayama_scraper.snapshots.snapshot import SnapshotState
from amayama_scraper.transport.port import BrowserCapture

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

# a manifest with a single declared category/expected group, so accepting
# that one group completes the collection immediately.
MANIFEST_HTML = """
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


def _capture(html: str, url: str) -> BrowserCapture:
    return BrowserCapture(page_source=html, effective_url=url, captured_at=datetime.now(UTC))


def test_full_manifest_plus_group_detail_auto_finalizes(tmp_path: Path):
    conn = connect(str(tmp_path / "db.sqlite3"))
    run_migrations(conn)
    # source/manufacturer/vehicle_model/market precisam bater com
    # AMAROK_CONTEXT (004: process_capture()/try_finalize_spec_entry()
    # validam spec_key -> context antes de qualquer persistência).
    key = save_spec_identity(
        conn,
        SpecIdentity(
            source="AMAYAMA",
            manufacturer="VOLKSWAGEN",
            vehicle_model="AMAROK",
            market="AMA-BR",
            model_code="E",
            amayama_catalog_id="F",
            production_period_raw="G",
            source_url="https://x/spec-1",
        ),
    )
    save_collection_run(conn, CollectionRun(run_id="run-1", scope=AMAROK_CONTEXT.scope()))
    blob_store = FilesystemRawBlobStore(tmp_path / "blobs", conn)
    capture_repo = SqliteRawCaptureRepository(conn)

    # run_collection_driver() always runs the MARKET_INDEX phase first,
    # unconditionally, before the spec loop (contracts/browser-transport-
    # contract.md §3) — its discoveries are irrelevant here (spec-1 was
    # already registered directly above; spec_filter below scopes to it).
    market_html = (FIXTURES / "market_index" / "same_model_code_diff_catalog.html").read_text(
        encoding="utf-8"
    )
    market_url = "https://www.amayama.com/en/genuine-catalogs/epc/volkswagen-overall/amarok/ama-br"

    transport = FakeBrowserTransport()
    transport.queue_navigate(_capture(market_html, market_url))
    transport.queue_navigate(_capture(MANIFEST_HTML, "https://x/spec-1"))
    transport.queue_navigate(_capture(MANIFEST_HTML, "https://x/front-axle-steering"))
    transport.queue_navigate(_capture(GROUP_HTML, "https://x/front-axle-steering/407"))

    run_collection_driver(
        transport,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        context=AMAROK_CONTEXT,
        filters=OperationalFilters(spec_filter=[key]),
    )

    current = get_current_state(conn, key)
    assert current is not None
    snapshot_row = conn.execute(
        "SELECT state FROM spec_snapshot WHERE snapshot_id = ?", (current.latest_snapshot_id,)
    ).fetchone()
    assert snapshot_row["state"] == SnapshotState.VALID.value
