"""T053 — accept_capture() writes RawBlob+RawCapture before any validation."""

from datetime import UTC, datetime

from tests.unit.fakes import InMemoryRawBlobStore, InMemoryRawCaptureRepository

from amayama_scraper.ingestion.accept import accept_capture
from amayama_scraper.ingestion.capture_input import RawCaptureInput
from amayama_scraper.ingestion.capture_kind import CaptureKind
from amayama_scraper.ingestion.hashing import content_hash


def make_input(**overrides: object) -> RawCaptureInput:
    defaults: dict[str, object] = dict(
        capture_kind=CaptureKind.GROUP_DETAIL,
        source_url="https://amayama.example/group/407",
        collected_at=datetime(2026, 8, 26, tzinfo=UTC),
        raw_content=b"<html>content</html>",
        run_id="run-1",
    )
    defaults.update(overrides)
    return RawCaptureInput(**defaults)  # type: ignore[arg-type]


def test_accept_capture_persists_blob_and_capture():
    blob_store = InMemoryRawBlobStore()
    capture_repo = InMemoryRawCaptureRepository()
    capture_input = make_input()

    capture = accept_capture(capture_input, blob_store, capture_repo)

    expected_hash = content_hash(capture_input.raw_content)
    assert capture.content_hash == expected_hash
    assert blob_store.read(expected_hash) == capture_input.raw_content
    assert capture_repo.get(capture.capture_id) == capture


def test_accept_capture_preserves_raw_regardless_of_downstream_validation():
    """Raw is preserved unconditionally — validation happens as a separate step."""
    blob_store = InMemoryRawBlobStore()
    capture_repo = InMemoryRawCaptureRepository()
    capture_input = make_input(raw_content=b"<html>this will later be classified CHALLENGE</html>")

    capture = accept_capture(capture_input, blob_store, capture_repo)

    assert blob_store.read(capture.content_hash) == capture_input.raw_content
