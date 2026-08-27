# Regression fixtures — real Amayama evidence (AMA-BR)

This directory holds the regression tests for the four reference-evidence
pairs mandated by the Constitution (§12 — "Regressões dos pares Amarok já
estudados devem virar fixtures/testes de referência") and by
`tasks.md` T245–T249. Fixture HTML lives under
`tests/fixtures/regression/<spec-slug>/`.

## DEC-004 — sampling strategy (PO-approved, 2026-08-27)

The original T245–T248 wording required materializing **every** real
group-detail page for each controlled spec. The PO revised this via
**DEC-004** (`specs/001-amarok-ama-br-ingestion/spec.md` §Decisions):

- real, **complete** SPEC_NAVIGATION manifests remain mandatory for every
  controlled spec — no exception;
- the group-details kept permanently in the repository become a **small,
  real, representative sample** — not the full catalog;
- a test may only assert `EXACT` about evidence it actually materialized
  — never extrapolated to the whole EPC;
- the sample is never presented as isolated proof of whole-catalog
  equivalence;
- historical evidence of full-catalog comparison may remain documented as
  research, but must never be simulated by artificial fixtures;
- no production logic may hardcode model codes, catalog IDs, or specific
  pairs — catalog codes appear only as test/regression data;
- no CAPTCHA/Cloudflare bypass automation is part of the feature;
  acquisition stays browser-assisted/human-in-the-loop (DEC-001).

## SAMPLE-LEVEL EXACT vs. WHOLE-SPEC EXACT (2026-08-27 clarification)

T245–T247 prove **SAMPLE-LEVEL EXACT**, not WHOLE-SPEC EXACT. These are
deliberately different claims, proven by different real code paths:

**SAMPLE-LEVEL EXACT** (what T245–T247 actually assert): the specific
real group-detail pages captured for a pair produce identical part
content, proven by running them through the real, unmodified functions —

```
parse_spec_group_manifest() / parse_group_detail()
  -> apply_normalization()
  -> part_fingerprint() / group_fingerprint() / category_fingerprint()
```

— and comparing the resulting fingerprints directly. No `SpecSnapshot` is
built or fabricated for this claim, and none of `finalize_spec_entry()`,
`compute_collection_complete()`, or `evaluate_equivalence()` are touched,
modified, or relaxed to produce it.

**WHOLE-SPEC EXACT** (what T245–T247 do *not* claim): a `parts_relation
== EXACT` verdict from `evaluate_equivalence()` on two real
`SpecSnapshot`s. This requires `collection_complete=True` on both sides —
i.e. *every* `(category, group)` pair declared by the real, complete
manifest (108 groups for `2hbc3x`/`s1bc3x`/`s6bc74`/`s7bc74`/`s7bc8a-61189`,
99 for `s7bc8a-62184`/`agdc8a-62169`) actually `ACCEPTED`, not a 2–4 group
sample. `compute_collection_complete()`, `finalize_spec_entry()`, and
`evaluate_equivalence()` are untouched, unrelaxed, and still mean exactly
what they meant before this session: a spec with only a sample collected
legitimately produces `state=INCOMPLETE`, and comparing two `INCOMPLETE`
snapshots legitimately yields `comparison_valid=False` /
`parts_relation=PartsRelation.UNKNOWN`. That remains the correct behavior
of the unmodified pipeline and is not something these tests route around,
mask, or reinterpret.

## Resolved follow-up — Issue #8 (g-recaptcha false positive)

Full, untrimmed real Amayama pages (the manifests and group-detail pages
materialized for T245–T247) used to trip `validation/detectors/challenge.py`'s
`CHALLENGE` detector as a **false positive**: Amayama's real page template
embeds a hidden Sign-Up/Restore-password modal on every page (not just
challenge pages), which contains a `<div class="g-recaptcha">` widget
inside `#registration-form-container`/`#restore-form-container`, unrelated
to any actual bot challenge. The original `_ID_OR_CLASS_MARKERS` substring
check flagged `"g-recaptcha"` unconditionally, so `classify_capture()`
misclassified these genuinely valid pages as `CHALLENGE`.

This was fixed under Issue #8 (PO-approved scope, separate from Phase 16):
`detect_challenge()` now locates `.g-recaptcha` elements via the DOM
(BeautifulSoup) instead of a raw substring, and ignores only the ones whose
ancestor is `#registration-form-container` or `#restore-form-container`; a
`.g-recaptcha` anywhere else still counts as a challenge signal exactly as
before. `classify.py`, `finalize_spec_entry()`, `compute_collection_complete()`,
and `evaluate_equivalence()` were not touched. Regression coverage:
`tests/parser/test_challenge_detection.py` (real `2hbc3x` manifest and
`engine/100` page now classify as `ACCEPTED`, not `CHALLENGE`; a minimal
`.g-recaptcha` outside both containers is still detected; the existing
`challenge_cloudflare.html` case is unaffected).

T245–T247 still do not depend on this fix — they never called
`process_capture()`/`classify_capture()`/`finalize_spec_entry()` in the
first place (SAMPLE-LEVEL EXACT does not require them, see above); the fix
matters for future evidence acquisition/ingestion generally, not for these
tests specifically.

## Evidence inventory

All HTML below is real, browser-assisted/human-in-the-loop acquisition
(DEC-001) from the live Amayama AMA-BR EPC for the Volkswagen Amarok.
CAPTCHA/Cloudflare, when encountered during acquisition, was resolved
manually by a human in the loop — no automated bypass exists anywhere in
this feature, and Selenium/CDP is not part of the production transport
(`src/`); the temporary local collector script(s) used to acquire this
evidence are explicitly not imported by, or a dependency of, this feature.

| Spec (slug) | model_code | amayama_catalog_id | manifest.html | groups sampled | real groups declared |
|---|---|---|---|---|---|
| `2hbc3x` | 2HBC3X | 56060 | ✅ | `engine/100`, `front-axle-steering/407`, `body/800` | 108 |
| `s1bc3x` | S1BC3X | 56087 | ✅ | `engine/100`, `front-axle-steering/407`, `body/800` | 108 |
| `s6bc74` | S6BC74 | 61127 | ✅ | `engine/100`, `front-axle-steering/407`, `body/800`, `access-infotainment-miscell/019` | 108 |
| `s7bc74` | S7BC74 | 61187 | ✅ | `engine/100`, `front-axle-steering/407`, `body/800`, `access-infotainment-miscell/019` | 108 |
| `s7bc8a-62184` | S7BC8A | 62184 | ✅ | `engine/100`, `front-axle-steering/407`, `body/800` | 99 |
| `agdc8a-62169` | AGDC8A | 62169 | ✅ | `engine/100`, `front-axle-steering/407`, `body/800` | 99 |
| `s7bc8a-61189` | S7BC8A | 61189 | ✅ (documentary — see T248) | none | 108 |

`s7bc8a-61189`'s manifest is materialized as complementary/documentary
evidence (its group_count matches the collector's acquisition report) but
is not wired into any assertion — T248 does not need it (see below).

### Per-pair findings

- **T245 (`2hbc3x` ↔ `s1bc3x`)**: `engine/100` (recaptured this session —
  the two earlier files pointed to by an older evidence set were, on
  inspection, real Cloudflare challenge pages (`title="Um momento…"`,
  27,791 bytes, fail `parse_group_detail()`'s structural marker) and were
  discarded, never used as fixtures or evidence), `front-axle-steering/407`
  and `body/800` are all SAMPLE-LEVEL EXACT for parts.
- **T246 (`s6bc74` ↔ `s7bc74`)**: `engine/100`, `front-axle-steering/407`
  and `body/800` are SAMPLE-LEVEL EXACT for parts, and **neither side
  shows any image** on those three groups — the "difference is only in
  image" scenario from the original task wording is not sustained by
  those three groups, and is not forced. The real group that *does*
  sustain it is `access-infotainment-miscell/019`: SAMPLE-LEVEL EXACT
  parts, with a genuine image asymmetry on schemas `19010`/`19011` (none
  on `s6bc74`, present on `s7bc74`) — proven via `part_fingerprint()`
  equality (image-independent) plus `image_hash()` inequality
  (image-only channel), per Constitution §8/§10.
- **T247 (`s7bc8a-62184` ↔ `agdc8a-62169`)**: `engine/100`,
  `front-axle-steering/407` and `body/800` are SAMPLE-LEVEL EXACT for
  parts. `body/800` additionally shows real, complete image
  complementarity: `s7bc8a-62184` has zero own images across all 6 real
  schemas, `agdc8a-62169` has an own image on all 6 — proven the same way
  as T246, at sample scope, without fabricating a `SpecSnapshot`.
- **T248 (`S7BC8A-62184` vs `S7BC8A-61189`)**: proves `model_code` alone
  is never sufficient identity (FR-003, Constitution §2). No real
  manifest or group-detail evidence for `S7BC8A-61189` existed anywhere
  in the workspace at the time this task was implemented (confirmed by
  exhaustive filesystem + git-history search) — the identity property
  under test does not require them anyway, since `SpecIdentity` is built
  from MARKET_INDEX-level fields (`model_code`, `amayama_catalog_id`,
  `source_url`), never from group-detail/parts content. Implemented
  exclusively via the already-approved real MARKET_INDEX fixture
  (`tests/fixtures/market_index/same_model_code_diff_catalog.html`,
  DEC-001) through `parse_market_spec_index()` → `DiscoveredSpecEntry` →
  `SpecIdentity.stable_key()`. `s7bc8a-61189`'s manifest, materialized
  later in this session, is kept only as complementary/documentary
  evidence and changes nothing about T248's implementation.

## Fixture layout

```
tests/fixtures/regression/<spec-slug>/manifest.html          # real, complete SPEC_NAVIGATION
tests/fixtures/regression/<spec-slug>/<category>/<group>.html # real, sampled GROUP_DETAIL
```

`S7BC8A` has two real, distinct catalog identities (`62184` and `61189`);
the fixture path disambiguates them by slug (`s7bc8a-62184/` vs.
`s7bc8a-61189/`) — never by `model_code` alone, matching the identity rule
under test in T248.

Fixtures unrelated to this Phase 16 sample (e.g. the Phase 1/4/6 unit-test
fixtures under `tests/fixtures/market_index/`, `tests/fixtures/spec_navigation/`,
`tests/fixtures/group_detail/`) are either real-derived-and-trimmed
(labeled `REAL-DERIVED TEST FIXTURE` in their own HTML comment header,
per DEC-001) or synthetic-and-labeled; none of them are presented as
Phase 16 regression evidence.

## No hardcoding

No production code (`src/`) references `2H`/`S1`/`S6`/`S7`/`AGD`/
`S7BC8A`/`AGDC8A`, any `amayama_catalog_id`, or any specific pair. The
tests in this directory validate behavior that emerges from real content
run through generic, already-implemented parsing/normalization/
fingerprint/identity code — the catalog codes above appear only as test
fixture data and in this documentation.
