"""T260 — log nunca contém raw_content completo, apenas referência
(content_hash/caminho) — research.md §14."""

import json

import pytest

from amayama_scraper.orchestration.logging import RawContentInLogError, log_event


def test_log_event_emits_json_line_correlated_by_run_id():
    lines: list[str] = []
    log_event(run_id="run-1", event="capture_accepted", emit=lines.append, capture_id="cap-1")

    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["run_id"] == "run-1"
    assert payload["event"] == "capture_accepted"
    assert payload["capture_id"] == "cap-1"


def test_log_event_rejects_raw_content_field_by_name():
    with pytest.raises(RawContentInLogError):
        log_event(run_id="run-1", event="x", emit=lambda _: None, raw_content=b"<html>...</html>")


def test_log_event_rejects_any_bytes_valued_field_even_if_not_named_raw_content():
    with pytest.raises(RawContentInLogError):
        log_event(run_id="run-1", event="x", emit=lambda _: None, payload=b"some bytes")


def test_log_event_accepts_a_reference_instead_of_the_raw_bytes():
    lines: list[str] = []
    log_event(
        run_id="run-1",
        event="capture_accepted",
        emit=lines.append,
        content_hash="a" * 64,
        size_bytes=1234,
    )
    payload = json.loads(lines[0])
    assert payload["content_hash"] == "a" * 64
    assert payload["size_bytes"] == 1234
