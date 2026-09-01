"""T050 — falha de transporte nunca produz um CheckpointEntry com
evidence.outcome (data-model.md §3, DEC-006).

Uma falha de `transport.navigate()`/`current_capture()` acontece ANTES de
qualquer `RawCaptureInput` existir — `process_capture()` nunca é chamado
nesse caminho (contracts/browser-transport-contract.md §3: a conversão
BrowserCapture -> RawCaptureInput só ocorre após uma captura bem-sucedida).
Este teste prova essa propriedade usando as peças reais (FakeBrowserTransport,
checkpoint_repo, process_capture) sem depender do driver completo (Fase 8),
exatamente como tasks.md T050 exige (depende apenas de T023/T046).
"""

from __future__ import annotations

from datetime import UTC, datetime

from tests.unit.fakes import (
    FakeBrowserTransport,
    InMemoryRawBlobStore,
    InMemoryRawCaptureRepository,
)

from amayama_scraper.checkpoint.collection_run import CollectionRun
from amayama_scraper.ingestion.capture_input import RawCaptureInput
from amayama_scraper.ingestion.capture_kind import AcquisitionMode, CaptureKind
from amayama_scraper.orchestration.pipeline import process_capture
from amayama_scraper.orchestration.retry_classification import (
    PendingUnitClassification,
    classify_pending_unit,
)
from amayama_scraper.persistence.db import connect
from amayama_scraper.persistence.migrations.runner import run_migrations
from amayama_scraper.persistence.repositories.checkpoint_repo import (
    get_checkpoint_entry,
    save_collection_run,
)
from amayama_scraper.transport.errors import ChromeNotReachableError
from amayama_scraper.transport.port import BrowserCapture


def _attempt_group_detail(
    transport, conn, blob_store, capture_repo, *, run_id, spec_key, category_slug, group_id, url
):
    """Réplica mínima do padrão que o driver (Fase 8) seguirá: uma falha de
    transporte nunca alcança process_capture()."""
    try:
        capture = transport.navigate(url)
    except Exception:
        return "transport_failure", None
    capture_input = RawCaptureInput(
        capture_kind=CaptureKind.GROUP_DETAIL,
        source_url=capture.effective_url,
        collected_at=capture.captured_at,
        raw_content=capture.page_source.encode("utf-8"),
        run_id=run_id,
        acquisition_mode=AcquisitionMode.AUTOMATED_BROWSER_CDP,
    )
    result = process_capture(
        conn,
        blob_store,
        capture_repo,
        run_id,
        capture_input,
        category_slug=category_slug,
        group_id=group_id,
        spec_key=spec_key,
    )
    return "processed", result


def test_transport_failure_never_calls_process_capture_or_writes_checkpoint():
    conn = connect(":memory:")
    run_migrations(conn)
    save_collection_run(conn, CollectionRun(run_id="run-1"))
    blob_store = InMemoryRawBlobStore()
    capture_repo = InMemoryRawCaptureRepository()

    transport = FakeBrowserTransport()
    transport.queue_navigate(ChromeNotReachableError("Chrome lost"))

    outcome, result = _attempt_group_detail(
        transport,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        spec_key="spec-1",
        category_slug="engine",
        group_id="1",
        url="https://x/engine/1",
    )

    assert outcome == "transport_failure"
    assert result is None
    # no CheckpointEntry was ever created as a result of this failed attempt
    assert get_checkpoint_entry(conn, "run-1", "spec-1", "engine", "1") is None
    # so the unit is still classified as never attempted, not as a rejection
    assert classify_pending_unit(None) is PendingUnitClassification.NOT_YET_ATTEMPTED


def test_transport_failure_after_a_prior_rejection_leaves_the_rejection_untouched():
    """A REQUIRES_EXPLICIT_RETRY unit retried manually, whose retry attempt
    then fails at the transport level, must not silently lose its prior
    validation-rejection evidence."""
    conn = connect(":memory:")
    run_migrations(conn)
    save_collection_run(conn, CollectionRun(run_id="run-1"))
    blob_store = InMemoryRawBlobStore()
    capture_repo = InMemoryRawCaptureRepository()

    # First attempt: a real INVALID capture, processed normally.
    transport = FakeBrowserTransport()
    transport.queue_navigate(
        BrowserCapture(
            page_source="<html>not epc content</html>",
            effective_url="https://x/engine/1",
            captured_at=datetime.now(UTC),
        )
    )
    _attempt_group_detail(
        transport,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        spec_key="spec-1",
        category_slug="engine",
        group_id="1",
        url="https://x/engine/1",
    )
    before = get_checkpoint_entry(conn, "run-1", "spec-1", "engine", "1")
    assert before is not None
    assert classify_pending_unit(before) is PendingUnitClassification.REQUIRES_EXPLICIT_RETRY

    # Manual retry attempt fails at the transport level.
    transport.queue_navigate(ChromeNotReachableError("Chrome lost mid-retry"))
    outcome, _ = _attempt_group_detail(
        transport,
        conn,
        blob_store,
        capture_repo,
        run_id="run-1",
        spec_key="spec-1",
        category_slug="engine",
        group_id="1",
        url="https://x/engine/1",
    )

    assert outcome == "transport_failure"
    after = get_checkpoint_entry(conn, "run-1", "spec-1", "engine", "1")
    assert after == before  # untouched — the prior rejection evidence is preserved
