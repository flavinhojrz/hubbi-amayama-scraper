"""T092/T093 — non-ACCEPTED captures never reach any of the three parsers
(Nível A/B/C) — contracts/input-contracts.md invariante."""

from pathlib import Path
from unittest.mock import patch

from amayama_scraper.ingestion.capture_kind import CaptureKind
from amayama_scraper.parsing.group_detail import parse_group_detail
from amayama_scraper.parsing.market_index import parse_market_spec_index
from amayama_scraper.parsing.spec_group_manifest import parse_spec_group_manifest
from amayama_scraper.validation.classify import classify_capture
from amayama_scraper.validation.types import ValidationOutcome

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

_PARSE_TARGETS = {
    CaptureKind.MARKET_INDEX: (
        "tests.integration.test_parser_never_reached_on_rejected_capture.parse_market_spec_index"
    ),
    CaptureKind.SPEC_NAVIGATION: (
        "tests.integration.test_parser_never_reached_on_rejected_capture.parse_spec_group_manifest"
    ),
    CaptureKind.GROUP_DETAIL: (
        "tests.integration.test_parser_never_reached_on_rejected_capture.parse_group_detail"
    ),
}


def _maybe_parse(raw_content: bytes, capture_kind: CaptureKind, category_slug: str, group_id: str):
    """Minimal gate mirroring what orchestration (Phase 14) will do: only
    ACCEPTED captures are handed to a parser — routed by capture_kind."""
    result = classify_capture(raw_content, capture_kind)
    if result.primary_outcome is not ValidationOutcome.ACCEPTED:
        return result, None
    text = raw_content.decode("utf-8")
    if capture_kind is CaptureKind.MARKET_INDEX:
        return result, parse_market_spec_index(text, source_capture_id="cap")
    if capture_kind is CaptureKind.SPEC_NAVIGATION:
        return result, parse_spec_group_manifest(text, spec_key="spec-1", source_capture_id="cap")
    return result, parse_group_detail(text, category_slug=category_slug, group_id=group_id)


def test_challenge_never_reaches_any_parser():
    html = (FIXTURES / "challenge_cloudflare.html").read_bytes()
    with (
        patch(_PARSE_TARGETS[CaptureKind.MARKET_INDEX]) as spy_a,
        patch(_PARSE_TARGETS[CaptureKind.SPEC_NAVIGATION]) as spy_b,
        patch(_PARSE_TARGETS[CaptureKind.GROUP_DETAIL]) as spy_c,
    ):
        for capture_kind in (
            CaptureKind.MARKET_INDEX,
            CaptureKind.SPEC_NAVIGATION,
            CaptureKind.GROUP_DETAIL,
        ):
            validation, parsed = _maybe_parse(html, capture_kind, "c", "1")
            assert validation.primary_outcome is ValidationOutcome.CHALLENGE
            assert parsed is None
        spy_a.assert_not_called()
        spy_b.assert_not_called()
        spy_c.assert_not_called()


def test_translation_contaminated_never_reaches_any_parser():
    html = (FIXTURES / "translation_contaminated.html").read_bytes()
    with (
        patch(_PARSE_TARGETS[CaptureKind.MARKET_INDEX]) as spy_a,
        patch(_PARSE_TARGETS[CaptureKind.SPEC_NAVIGATION]) as spy_b,
        patch(_PARSE_TARGETS[CaptureKind.GROUP_DETAIL]) as spy_c,
    ):
        for capture_kind in (
            CaptureKind.MARKET_INDEX,
            CaptureKind.SPEC_NAVIGATION,
            CaptureKind.GROUP_DETAIL,
        ):
            validation, parsed = _maybe_parse(html, capture_kind, "c", "1")
            assert validation.primary_outcome is ValidationOutcome.TRANSLATION_CONTAMINATED
            assert parsed is None
        spy_a.assert_not_called()
        spy_b.assert_not_called()
        spy_c.assert_not_called()


def test_incomplete_never_reaches_group_detail_parser():
    # incomplete_capture.html is shaped as a truncated GROUP_DETAIL page — its
    # INCOMPLETE signal is only meaningful (i.e. not pre-empted by a structural
    # INVALID from a mismatched capture_kind, DEC-003 precedence) under its own
    # capture_kind. What must hold for every capture_kind is the invariant this
    # test targets: a non-ACCEPTED outcome never reaches the parser.
    html = (FIXTURES / "incomplete_capture.html").read_bytes()
    with patch(_PARSE_TARGETS[CaptureKind.GROUP_DETAIL]) as spy_c:
        validation, parsed = _maybe_parse(html, CaptureKind.GROUP_DETAIL, "c", "1")
        assert validation.primary_outcome is ValidationOutcome.INCOMPLETE
        assert parsed is None
        spy_c.assert_not_called()


def test_non_accepted_outcome_never_reaches_any_parser_regardless_of_kind():
    html = (FIXTURES / "incomplete_capture.html").read_bytes()
    with (
        patch(_PARSE_TARGETS[CaptureKind.MARKET_INDEX]) as spy_a,
        patch(_PARSE_TARGETS[CaptureKind.SPEC_NAVIGATION]) as spy_b,
        patch(_PARSE_TARGETS[CaptureKind.GROUP_DETAIL]) as spy_c,
    ):
        for capture_kind in (
            CaptureKind.MARKET_INDEX,
            CaptureKind.SPEC_NAVIGATION,
            CaptureKind.GROUP_DETAIL,
        ):
            validation, parsed = _maybe_parse(html, capture_kind, "c", "1")
            assert validation.primary_outcome is not ValidationOutcome.ACCEPTED
            assert parsed is None
        spy_a.assert_not_called()
        spy_b.assert_not_called()
        spy_c.assert_not_called()


def test_accepted_does_reach_group_detail_parser():
    html = (FIXTURES / "group_detail" / "valid_group_detail.html").read_bytes()
    validation, parsed = _maybe_parse(html, CaptureKind.GROUP_DETAIL, "front-axle-steering", "407")
    assert validation.primary_outcome is ValidationOutcome.ACCEPTED
    assert parsed is not None
    assert parsed.critical_error is None


def test_accepted_does_reach_market_index_parser():
    html = (FIXTURES / "market_index" / "valid_multi_entry.html").read_bytes()
    validation, parsed = _maybe_parse(html, CaptureKind.MARKET_INDEX, "", "")
    assert validation.primary_outcome is ValidationOutcome.ACCEPTED
    assert parsed is not None
    assert parsed.critical_error is None


def test_accepted_does_reach_spec_group_manifest_parser():
    html = (FIXTURES / "spec_navigation" / "valid_manifest.html").read_bytes()
    validation, parsed = _maybe_parse(html, CaptureKind.SPEC_NAVIGATION, "", "")
    assert validation.primary_outcome is ValidationOutcome.ACCEPTED
    assert parsed is not None
    assert parsed.critical_error is None
