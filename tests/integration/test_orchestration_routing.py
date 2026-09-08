"""T235 — process_capture() roteia corretamente cada capture_kind; ACCEPTED segue
o pipeline completo; CHALLENGE/TRANSLATION_CONTAMINATED/INVALID/INCOMPLETE param
antes de qualquer parser (contracts/input-contracts.md)."""

from datetime import UTC, datetime
from pathlib import Path

from tests.support import AMAROK_CONTEXT, register_spec

from amayama_scraper.checkpoint.checkpoint_entry import CheckpointStatus
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
from amayama_scraper.persistence.repositories.checkpoint_repo import (
    get_checkpoint_entry,
    save_collection_run,
)
from amayama_scraper.persistence.repositories.spec_registry_repo import (
    find_by_model_code_and_catalog_id,
)
from amayama_scraper.validation.types import ValidationOutcome

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _setup(tmp_path: Path):
    conn = connect(str(tmp_path / "db.sqlite3"))
    run_migrations(conn)
    save_collection_run(conn, CollectionRun(run_id="run-1"))
    blob_store = FilesystemRawBlobStore(tmp_path / "blobs", conn)
    capture_repo = SqliteRawCaptureRepository(conn)
    return conn, blob_store, capture_repo


def test_market_index_accepted_registers_discovered_entries(tmp_path: Path):
    conn, blob_store, capture_repo = _setup(tmp_path)
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

    found = find_by_model_code_and_catalog_id(conn, "AGDA43", "62158")
    assert len(found) == 1


def test_spec_navigation_accepted_saves_manifest(tmp_path: Path):
    conn, blob_store, capture_repo = _setup(tmp_path)
    register_spec(conn, "spec-1", AMAROK_CONTEXT)
    html = (FIXTURES / "spec_navigation" / "valid_manifest.html").read_bytes()

    result = process_capture(
        conn,
        blob_store,
        capture_repo,
        "run-1",
        RawCaptureInput(
            capture_kind=CaptureKind.SPEC_NAVIGATION,
            source_url="https://www.amayama.com/en/x/s1bc3x-56087",
            collected_at=datetime.now(UTC),
            raw_content=html,
            run_id="run-1",
        ),
        context=AMAROK_CONTEXT,
        spec_key="spec-1",
    )

    assert result.validation_outcome is ValidationOutcome.ACCEPTED
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM spec_group_manifest WHERE spec_key = ?", ("spec-1",)
    ).fetchone()
    assert row["c"] == 1


def test_group_detail_accepted_marks_checkpoint_accepted(tmp_path: Path):
    conn, blob_store, capture_repo = _setup(tmp_path)
    register_spec(conn, "spec-1", AMAROK_CONTEXT)
    html = (FIXTURES / "group_detail" / "valid_group_detail.html").read_bytes()

    result = process_capture(
        conn,
        blob_store,
        capture_repo,
        "run-1",
        RawCaptureInput(
            capture_kind=CaptureKind.GROUP_DETAIL,
            source_url="https://x/407",
            collected_at=datetime.now(UTC),
            raw_content=html,
            run_id="run-1",
        ),
        context=AMAROK_CONTEXT,
        category_slug="front-axle-steering",
        group_id="407",
        spec_key="spec-1",
    )

    assert result.validation_outcome is ValidationOutcome.ACCEPTED
    assert result.routed_to_parser is True

    entry = get_checkpoint_entry(conn, "run-1", "spec-1", "front-axle-steering", "407")
    assert entry is not None
    assert entry.status == CheckpointStatus.ACCEPTED
    assert entry.raw_capture_id == result.capture_id


def test_challenge_capture_never_reaches_any_parser_and_group_detail_is_rejected(
    tmp_path: Path,
):
    conn, blob_store, capture_repo = _setup(tmp_path)
    register_spec(conn, "spec-1", AMAROK_CONTEXT)
    html = (FIXTURES / "challenge_cloudflare.html").read_bytes()

    result = process_capture(
        conn,
        blob_store,
        capture_repo,
        "run-1",
        RawCaptureInput(
            capture_kind=CaptureKind.GROUP_DETAIL,
            source_url="https://x/407",
            collected_at=datetime.now(UTC),
            raw_content=html,
            run_id="run-1",
        ),
        context=AMAROK_CONTEXT,
        category_slug="front-axle-steering",
        group_id="407",
        spec_key="spec-1",
    )

    assert result.validation_outcome is ValidationOutcome.CHALLENGE
    assert result.routed_to_parser is False

    entry = get_checkpoint_entry(conn, "run-1", "spec-1", "front-axle-steering", "407")
    assert entry is not None
    assert entry.status == CheckpointStatus.REJECTED


def test_challenge_capture_for_market_index_never_reaches_parser(tmp_path: Path):
    conn, blob_store, capture_repo = _setup(tmp_path)
    html = (FIXTURES / "challenge_cloudflare.html").read_bytes()

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

    assert result.validation_outcome is ValidationOutcome.CHALLENGE
    assert result.routed_to_parser is False
    row = conn.execute("SELECT COUNT(*) AS c FROM spec_registry").fetchone()
    assert row["c"] == 0
