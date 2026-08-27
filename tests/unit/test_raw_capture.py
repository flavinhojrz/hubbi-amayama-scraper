"""T027 — RawCapture immutability and observation distinctness (data-model.md §4b)."""

import hashlib
import uuid
from datetime import UTC, datetime

import pytest

from amayama_scraper.ingestion.capture_kind import CaptureKind
from amayama_scraper.ingestion.raw_capture import RawCapture


def make_capture(**overrides: object) -> RawCapture:
    defaults: dict[str, object] = dict(
        capture_id=str(uuid.uuid4()),
        run_id=str(uuid.uuid4()),
        content_hash=hashlib.sha256(b"hello").hexdigest(),
        source_url="https://amayama.example/group/407",
        collected_at=datetime(2026, 8, 26, tzinfo=UTC),
        capture_kind=CaptureKind.GROUP_DETAIL,
    )
    defaults.update(overrides)
    return RawCapture(**defaults)  # type: ignore[arg-type]


def test_is_frozen():
    capture = make_capture()
    with pytest.raises(Exception):  # noqa: B017
        capture.source_url = "https://other"  # type: ignore[misc]


def test_two_captures_same_content_hash_get_distinct_capture_ids():
    content_hash = hashlib.sha256(b"same bytes").hexdigest()
    a = make_capture(content_hash=content_hash)
    b = make_capture(content_hash=content_hash)
    assert a.content_hash == b.content_hash
    assert a.capture_id != b.capture_id  # never collapsed


def test_capture_kind_field_present():
    capture = make_capture(capture_kind=CaptureKind.MARKET_INDEX)
    assert capture.capture_kind == CaptureKind.MARKET_INDEX


@pytest.mark.parametrize("field_name", ["capture_id", "run_id", "content_hash", "source_url"])
def test_required_fields_cannot_be_empty(field_name: str) -> None:
    with pytest.raises(ValueError):
        make_capture(**{field_name: ""})
