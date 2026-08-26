"""T055 — two byte-identical captures produce one RawBlob, two distinct RawCapture."""

from datetime import UTC, datetime

from tests.unit.fakes import InMemoryRawBlobStore, InMemoryRawCaptureRepository

from amayama_scraper.ingestion.accept import accept_capture
from amayama_scraper.ingestion.capture_input import RawCaptureInput
from amayama_scraper.ingestion.capture_kind import CaptureKind


def make_input(**overrides: object) -> RawCaptureInput:
    defaults: dict[str, object] = dict(
        capture_kind=CaptureKind.GROUP_DETAIL,
        source_url="https://amayama.example/group/407",
        collected_at=datetime(2026, 8, 26, tzinfo=UTC),
        raw_content=b"<html>identical bytes</html>",
        run_id="run-1",
    )
    defaults.update(overrides)
    return RawCaptureInput(**defaults)  # type: ignore[arg-type]


def test_identical_content_single_blob_distinct_observations():
    blob_store = InMemoryRawBlobStore()
    capture_repo = InMemoryRawCaptureRepository()

    first = accept_capture(make_input(run_id="run-1"), blob_store, capture_repo)
    second = accept_capture(make_input(run_id="run-2"), blob_store, capture_repo)

    assert first.content_hash == second.content_hash
    assert first.capture_id != second.capture_id
    assert len(blob_store._blobs) == 1  # noqa: SLF001 - single physical blob
    assert capture_repo.get(first.capture_id) is not None
    assert capture_repo.get(second.capture_id) is not None
    assert first.run_id != second.run_id  # each observation keeps its own provenance
