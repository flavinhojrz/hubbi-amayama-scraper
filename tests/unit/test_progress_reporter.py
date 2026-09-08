"""T102/T104/T105 — progress_reporter (FR-027, research.md §15).

Reuso estrito de log_event() já existente — sem novo framework de logging.
Nunca vaza page_source/raw_content/html; agrega um resumo final."""

from __future__ import annotations

import json

import pytest

from amayama_scraper.orchestration.logging import RawContentInLogError
from amayama_scraper.orchestration.progress_reporter import make_terminal_reporter


def test_each_milestone_emits_one_json_line_with_correct_event() -> None:
    lines: list[str] = []
    on_event = make_terminal_reporter(run_id="run-1", emit=lines.append)

    on_event("RUN_STARTED", discovered=2, selected=1)
    on_event("SPEC_STARTED", spec_key="k1")
    on_event("GROUP_ACCEPTED", spec_key="k1", category_slug="engine", group_id="100")

    assert len(lines) == 3
    payloads = [json.loads(line) for line in lines]
    assert [p["event"] for p in payloads] == ["RUN_STARTED", "SPEC_STARTED", "GROUP_ACCEPTED"]
    assert all(p["run_id"] == "run-1" for p in payloads)


def test_never_leaks_raw_content_field() -> None:
    on_event = make_terminal_reporter(run_id="run-1", emit=lambda _line: None)
    with pytest.raises(RawContentInLogError):
        on_event("GROUP_ACCEPTED", raw_content=b"<html>should never be here</html>")


def test_run_summary_aggregates_counts_from_prior_events() -> None:
    lines: list[str] = []
    on_event = make_terminal_reporter(run_id="run-1", emit=lines.append)

    on_event("GROUP_ACCEPTED", spec_key="k1", category_slug="a", group_id="1")
    on_event("GROUP_ACCEPTED", spec_key="k1", category_slug="a", group_id="2")
    on_event("SPEC_SKIPPED_ALREADY_VALID", spec_key="k2")
    on_event("CHALLENGE_WAITING", source_url="https://x")
    on_event("GROUP_REJECTED", spec_key="k1", category_slug="a", group_id="3", outcome="INVALID")
    on_event("RUN_SUMMARY")

    summary_line = next(line for line in lines if "SUMMARY" in line and not line.startswith("{"))
    assert "ACCEPTED=2" in summary_line
    assert "SKIPPED=1" in summary_line
    assert "REJECTED=1" in summary_line
