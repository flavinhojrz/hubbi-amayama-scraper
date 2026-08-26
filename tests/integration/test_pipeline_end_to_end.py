"""T250 — pipeline completo MARKET_INDEX → SPEC_NAVIGATION → GROUP_DETAIL(s) →
normalize → fingerprints → snapshot → equivalence → image resolution, offline,
sem rede (quickstart.md Cenário 10)."""

from datetime import UTC, datetime
from pathlib import Path

from amayama_scraper.assets.fallback import resolve_image
from amayama_scraper.checkpoint.collection_run import CollectionRun
from amayama_scraper.domain.discovery import DiscoveredSpecEntry
from amayama_scraper.equivalence.cluster import build_equivalence_class
from amayama_scraper.equivalence.evaluate import evaluate_equivalence
from amayama_scraper.ingestion.capture_input import RawCaptureInput
from amayama_scraper.ingestion.capture_kind import CaptureKind
from amayama_scraper.orchestration.pipeline import CollectionInput, process_capture, run_collection
from amayama_scraper.persistence.adapters.filesystem_raw_blob_store import FilesystemRawBlobStore
from amayama_scraper.persistence.adapters.sqlite_raw_capture_repository import (
    SqliteRawCaptureRepository,
)
from amayama_scraper.persistence.db import connect
from amayama_scraper.persistence.migrations.runner import run_migrations
from amayama_scraper.persistence.repositories.checkpoint_repo import save_collection_run
from amayama_scraper.persistence.repositories.current_state_repo import get_current_state
from amayama_scraper.persistence.repositories.snapshot_repo import get_snapshot
from amayama_scraper.persistence.repositories.spec_registry_repo import (
    find_by_model_code_and_catalog_id,
)
from amayama_scraper.snapshots.snapshot import SnapshotState

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

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
        <div class="epcVariation__schema-name"><a href="https://x/front-axle-steering/407">407</a></div>
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


def _collect_one_spec(conn, blob_store, capture_repo, run_id: str, spec_key: str, oem: str):
    group_html = GROUP_HTML.replace("1K0407151", oem)
    save_collection_run(conn, CollectionRun(run_id=run_id))
    captures = [
        CollectionInput(
            capture_input=RawCaptureInput(
                capture_kind=CaptureKind.SPEC_NAVIGATION,
                source_url=f"https://x/{spec_key}",
                collected_at=datetime.now(UTC),
                raw_content=MANIFEST_HTML.encode("utf-8"),
                run_id=run_id,
            ),
            spec_key=spec_key,
        ),
        CollectionInput(
            capture_input=RawCaptureInput(
                capture_kind=CaptureKind.GROUP_DETAIL,
                source_url="https://x/front-axle-steering/407",
                collected_at=datetime.now(UTC),
                raw_content=group_html.encode("utf-8"),
                run_id=run_id,
            ),
            category_slug="front-axle-steering",
            group_id="407",
            spec_key=spec_key,
        ),
    ]
    return run_collection(conn, blob_store, capture_repo, run_id, captures)


def test_full_offline_pipeline_market_index_to_equivalence_and_image_resolution(
    tmp_path: Path,
):
    conn = connect(str(tmp_path / "db.sqlite3"))
    run_migrations(conn)
    save_collection_run(conn, CollectionRun(run_id="run-market"))
    blob_store = FilesystemRawBlobStore(tmp_path / "blobs", conn)
    capture_repo = SqliteRawCaptureRepository(conn)

    # 1. MARKET_INDEX (real-derived fixture, Nível A) -> DiscoveredSpecEntry registered
    market_html = (FIXTURES / "market_index" / "same_model_code_diff_catalog.html").read_bytes()
    market_result = process_capture(
        conn,
        blob_store,
        capture_repo,
        "run-market",
        RawCaptureInput(
            capture_kind=CaptureKind.MARKET_INDEX,
            source_url="https://www.amayama.com/en/x/ama-br",
            collected_at=datetime.now(UTC),
            raw_content=market_html,
            run_id="run-market",
        ),
    )
    assert market_result.routed_to_parser is True
    discovered = find_by_model_code_and_catalog_id(conn, "S7BC8A", "62184")
    assert len(discovered) == 1
    stable_key = discovered[0].stable_key()

    # 2. SPEC_NAVIGATION + GROUP_DETAIL for TWO specs with IDENTICAL part content
    #    -> proves equivalence (EXACT) end to end
    for spec_key in ("spec-a", "spec-b"):
        conn.execute(
            "INSERT OR IGNORE INTO spec_registry (stable_key, source, manufacturer, "
            "vehicle_model, market, model_code, amayama_catalog_id, production_period_raw, "
            "source_url) VALUES (?, 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H')",
            (spec_key,),
        )
    _collect_one_spec(conn, blob_store, capture_repo, "run-a", "spec-a", oem="1K0407151")
    _collect_one_spec(conn, blob_store, capture_repo, "run-b", "spec-b", oem="1K0407151")

    current_a = get_current_state(conn, "spec-a")
    current_b = get_current_state(conn, "spec-b")
    assert current_a is not None
    assert current_b is not None

    snapshot_a = get_snapshot(conn, current_a.latest_snapshot_id)
    snapshot_b = get_snapshot(conn, current_b.latest_snapshot_id)
    assert snapshot_a is not None
    assert snapshot_b is not None
    assert snapshot_a.state == SnapshotState.VALID
    assert snapshot_b.state == SnapshotState.VALID

    # 3. equivalence: identical part content -> EXACT
    scope = "AMAYAMA:VOLKSWAGEN:AMAROK:AMA-BR"
    result = evaluate_equivalence(snapshot_a, snapshot_b, scope_a=scope, scope_b=scope)
    assert result.comparison_valid is True
    assert result.parts_relation.value == "EXACT"

    # 4. cluster + image resolution: neither spec has its own image -> no fallback available
    cluster = build_equivalence_class(
        scope=scope,
        normalizer_version=snapshot_a.normalizer_version,
        fingerprint_version=snapshot_a.fingerprint_version,
        spec_parts_hash=snapshot_a.spec_parts_hash,
        member_spec_refs=("spec-a", "spec-b"),
        representative_spec_ref="spec-a",
    )
    resolved = resolve_image(
        spec_identity_ref="spec-b",
        own_image_refs=(),
        cluster=cluster,
        member_own_image_refs={"spec-a": ()},
    )
    assert resolved is None  # neither side has an own image in this fixture — legitimate None

    # sanity: DiscoveredSpecEntry.to_spec_identity() composes to the same stable_key style
    entry = DiscoveredSpecEntry(
        market="AMA-BR",
        model_code="S7BC8A",
        amayama_catalog_id="62184",
        source_url="https://x",
        source_capture_id="cap",
        production_period_raw="irrelevant for stable_key",
    )
    assert (
        entry.to_spec_identity(
            source="AMAYAMA", manufacturer="VOLKSWAGEN", vehicle_model="AMAROK"
        ).stable_key()
        == stable_key
    )
