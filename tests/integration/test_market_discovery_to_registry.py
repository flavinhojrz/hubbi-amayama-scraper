"""T253 — enumeração completa via MARKET_INDEX (Cenário 0) até SpecIdentity
registrada (FR-001; quickstart.md Cenário 0)."""

from datetime import UTC, datetime
from pathlib import Path

from tests.support import AMAROK_CONTEXT

from amayama_scraper.checkpoint.collection_run import CollectionRun
from amayama_scraper.ingestion.capture_input import RawCaptureInput
from amayama_scraper.ingestion.capture_kind import CaptureKind
from amayama_scraper.orchestration.pipeline import process_capture
from amayama_scraper.persistence.adapters.filesystem_raw_blob_store import FilesystemRawBlobStore
from amayama_scraper.persistence.adapters.sqlite_raw_capture_repository import (
    SqliteRawCaptureRepository,
)
from amayama_scraper.persistence.db import connect
from amayama_scraper.persistence.migrations.runner import run_migrations
from amayama_scraper.persistence.repositories.checkpoint_repo import save_collection_run
from amayama_scraper.persistence.repositories.spec_registry_repo import (
    find_by_model_code_and_catalog_id,
    get_spec_identity,
    list_discovered_spec_entries,
)
from amayama_scraper.validation.types import ValidationOutcome

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_market_index_capture_enumerates_and_registers_spec_identities(tmp_path: Path):
    conn = connect(str(tmp_path / "db.sqlite3"))
    run_migrations(conn)
    save_collection_run(conn, CollectionRun(run_id="run-1"))
    blob_store = FilesystemRawBlobStore(tmp_path / "blobs", conn)
    capture_repo = SqliteRawCaptureRepository(conn)

    html = (FIXTURES / "market_index" / "valid_multi_entry.html").read_bytes()
    result = process_capture(
        conn,
        blob_store,
        capture_repo,
        "run-1",
        RawCaptureInput(
            capture_kind=CaptureKind.MARKET_INDEX,
            source_url="https://www.amayama.com/en/x/ama-br",
            collected_at=datetime.now(UTC),
            raw_content=html,
            run_id="run-1",
        ),
        context=AMAROK_CONTEXT,
    )

    assert result.validation_outcome is ValidationOutcome.ACCEPTED
    assert result.routed_to_parser is True
    assert result.critical_error is False

    # 5 real-derived rows in this fixture -> 5 SpecIdentity registered
    total = conn.execute("SELECT COUNT(*) AS c FROM spec_registry").fetchone()["c"]
    assert total == 5

    found = find_by_model_code_and_catalog_id(conn, "AGDA43", "62158")
    assert len(found) == 1
    stable_key = found[0].stable_key()

    # full round trip: SpecIdentity retrievable by its own stable_key
    fetched = get_spec_identity(conn, stable_key)
    assert fetched is not None
    assert fetched.model_code == "AGDA43"
    assert fetched.market == "AMA-BR"

    # DiscoveredSpecEntry provenance preserved (source_capture_id links back
    # to the RawCapture that produced it)
    discovered_entries = list_discovered_spec_entries(conn, stable_key)
    assert len(discovered_entries) == 1
    assert discovered_entries[0].source_capture_id == result.capture_id
