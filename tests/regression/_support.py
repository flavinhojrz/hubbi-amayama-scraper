"""Shared test-only plumbing for T245-T247 SAMPLE-LEVEL EXACT regressions.

Not a test module itself (leading underscore keeps pytest from collecting
it). Scope, per DEC-004 and the 2026-08-27 clarification (spec.md
§Decisions): these regressions exercise `parse_spec_group_manifest()` /
`parse_group_detail()` -> real normalization -> `part_fingerprint()` /
`group_fingerprint()` / `category_fingerprint()` directly. They
deliberately do NOT go through `process_capture()`/`classify_capture()`
(a separate, documented, out-of-scope detector false-positive rejects full
untrimmed real pages as CHALLENGE — see tests/regression/README.md) nor
through `finalize_spec_entry()`/`SpecSnapshot`/`evaluate_equivalence()`
(WHOLE-SPEC equivalence requires full real collection_complete=True, which
this sample intentionally does not attempt — see DEC-004). No domain/
algorithm logic is reimplemented here, only fixture loading shared across
the three regression test files.
"""

from __future__ import annotations

from pathlib import Path

from amayama_scraper.domain.hierarchy import Category, Group, Schema
from amayama_scraper.parsing.group_detail import parse_group_detail
from amayama_scraper.parsing.results import ParsedGroupDetail, ParseManifestResult
from amayama_scraper.parsing.spec_group_manifest import parse_spec_group_manifest

REGRESSION_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "regression"


def load_manifest(spec_slug: str, spec_key: str) -> ParseManifestResult:
    html = (REGRESSION_FIXTURES / spec_slug / "manifest.html").read_text(encoding="utf-8")
    return parse_spec_group_manifest(html, spec_key=spec_key, source_capture_id=spec_key)


def load_group_detail(spec_slug: str, category_slug: str, group_id: str) -> ParsedGroupDetail:
    html = (REGRESSION_FIXTURES / spec_slug / category_slug / f"{group_id}.html").read_text(
        encoding="utf-8"
    )
    return parse_group_detail(html, category_slug, group_id)


def group_detail_to_category(
    category_slug: str, group_id: str, detail: ParsedGroupDetail
) -> Category:
    """Builds a single-group Category straight from real parsed content — the
    exact shape assemble_spec_tree() produces, just scoped to one sampled
    real group instead of the full manifest tree."""
    schemas = tuple(
        Schema(schema_id=s.schema_id, parts=tuple(p.to_part() for p in s.parts))
        for s in detail.schemas
    )
    return Category(
        category_slug=category_slug, groups=(Group(group_id=group_id, schemas=schemas),)
    )
