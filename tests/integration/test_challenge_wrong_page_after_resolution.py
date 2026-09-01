"""T060 — página errada após resolução (contracts/browser-transport-contract.md
§4, research.md §11).

O operador "navega" (via fake) para uma página que não corresponde à
estrutura esperada do capture_kind em curso; detect_invalid_structure()
real produz INVALID (nenhum detector novo é criado); a unidade vira
REQUIRES_EXPLICIT_RETRY e o laço não reentra automaticamente em novo poll
para ela."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from tests.unit.fakes import (
    FakeBrowserTransport,
)

from amayama_scraper.checkpoint.collection_run import CollectionRun
from amayama_scraper.ingestion.capture_kind import CaptureKind
from amayama_scraper.orchestration.collection_driver import await_challenge_resolution
from amayama_scraper.orchestration.retry_classification import (
    PendingUnitClassification,
    classify_pending_unit,
)
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
from amayama_scraper.transport.port import BrowserCapture
from amayama_scraper.validation.types import ValidationOutcome

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
CHALLENGE_HTML = (FIXTURES / "challenge_cloudflare.html").read_text(encoding="utf-8")
# A real page (e.g. the Amayama home page) that is neither a challenge nor
# the expected GROUP_DETAIL structure — plain HTML with none of the
# structural markers GROUP_DETAIL requires.
WRONG_PAGE_HTML = "<html><body><h1>Amayama — welcome</h1></body></html>"


def _capture(html: str) -> BrowserCapture:
    return BrowserCapture(
        page_source=html, effective_url="https://x/home", captured_at=datetime.now(UTC)
    )


def test_wrong_page_after_resolution_becomes_requires_explicit_retry_not_accepted(tmp_path):
    conn = connect(":memory:")
    run_migrations(conn)
    save_collection_run(conn, CollectionRun(run_id="run-1"))
    blob_store = FilesystemRawBlobStore(tmp_path, conn)
    capture_repo = SqliteRawCaptureRepository(conn)

    transport = FakeBrowserTransport()
    transport.queue_current_capture(_capture(CHALLENGE_HTML))
    transport.queue_current_capture(_capture(WRONG_PAGE_HTML))

    outcome = await_challenge_resolution(
        transport,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        capture_kind=CaptureKind.GROUP_DETAIL,
        source_url_hint="https://x/engine/1",
        category_slug="engine",
        group_id="1",
        spec_key="spec-1",
        poll_interval=0.0,
        sleep=lambda _s: None,
    )

    assert outcome.timed_out is False
    assert outcome.result is not None
    assert outcome.result.validation_outcome is ValidationOutcome.INVALID  # never ACCEPTED

    entry = get_checkpoint_entry(conn, "run-1", "spec-1", "engine", "1")
    assert entry is not None
    assert classify_pending_unit(entry) is PendingUnitClassification.REQUIRES_EXPLICIT_RETRY
