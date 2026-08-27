"""T058 — CHALLENGE detector against fixture (Constitution §5, FR-010).

Issue #8: `g-recaptcha` false positive on real, complete EPC pages — the
Amayama global template embeds a benign reCAPTCHA widget inside the
sign-up/restore-password modals (`#registration-form-container`,
`#restore-form-container`) on every page, unrelated to any actual
challenge.

Issue #8 (blocker material, Codex finding): the original fix determined
container membership exclusively via parsed DOM. In the real fixtures this
markup sits inside a `<script type="text/x-handlebars-template">` block,
which no spec-compliant HTML parser ever materializes as DOM — raw HTML
has 2 `g-recaptcha` occurrences, BeautifulSoup/lxml finds 0 `.g-recaptcha`
elements. Renaming the two approved container ids inside that same block
therefore slipped straight past the DOM-only check and still returned
`detected=False`/`ACCEPTED`. `test_renamed_container_ids_in_real_manifest_is_detected_as_challenge`
below reproduces that exact case against the real fixture.
"""

from pathlib import Path

from amayama_scraper.ingestion.capture_kind import CaptureKind
from amayama_scraper.validation.classify import classify_capture
from amayama_scraper.validation.detectors.challenge import detect_challenge
from amayama_scraper.validation.types import ValidationOutcome

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
REGRESSION_FIXTURES = FIXTURES / "regression"


def test_challenge_fixture_is_detected():
    html = (FIXTURES / "challenge_cloudflare.html").read_text()
    result = detect_challenge(html)
    assert result.detected is True
    assert result.evidence  # some signal must be recorded


def test_ordinary_page_not_detected_as_challenge():
    html = "<html><head><title>Amarok S7BC8A</title></head><body>ok</body></html>"
    result = detect_challenge(html)
    assert result.detected is False


def test_real_complete_manifest_g_recaptcha_in_benign_modal_is_not_challenge():
    """Caso 1 (Issue #8) — real, complete SPEC_NAVIGATION page."""
    html = (REGRESSION_FIXTURES / "2hbc3x" / "manifest.html").read_text(encoding="utf-8")
    assert "g-recaptcha" in html.lower()  # sanity: the benign widget is genuinely present

    result = detect_challenge(html)
    assert result.detected is False

    classification = classify_capture(html.encode("utf-8"), CaptureKind.SPEC_NAVIGATION)
    assert classification.primary_outcome is not ValidationOutcome.CHALLENGE
    assert classification.primary_outcome is ValidationOutcome.ACCEPTED


def test_real_complete_group_detail_g_recaptcha_in_benign_modal_is_not_challenge():
    """Caso 2 (Issue #8) — real, complete GROUP_DETAIL page."""
    html = (REGRESSION_FIXTURES / "2hbc3x" / "engine" / "100.html").read_text(encoding="utf-8")
    assert "g-recaptcha" in html.lower()  # sanity: the benign widget is genuinely present

    result = detect_challenge(html)
    assert result.detected is False

    classification = classify_capture(html.encode("utf-8"), CaptureKind.GROUP_DETAIL)
    assert classification.primary_outcome is not ValidationOutcome.CHALLENGE
    assert classification.primary_outcome is ValidationOutcome.ACCEPTED


def test_g_recaptcha_outside_benign_containers_is_still_a_challenge_signal():
    """Caso 3 (Issue #8) — minimal, non-fixture HTML: a `g-recaptcha` widget
    NOT nested inside a known benign modal container must still be detected."""
    html = """
    <html><head><title>ok</title></head>
    <body>
      <div id="some-unrelated-container">
        <div class="g-recaptcha" data-sitekey="anything"></div>
      </div>
    </body></html>
    """
    result = detect_challenge(html)
    assert result.detected is True
    assert "g-recaptcha" in result.evidence["id_or_class_markers"]


def test_g_recaptcha_inside_benign_containers_is_ignored_but_recorded():
    """Both benign containers together, no other signal — never detected,
    but the confirmed containers are recorded for observability."""
    html = """
    <html><head><title>ok</title></head>
    <body>
      <div id="registration-form-container">
        <div class="g-recaptcha" data-sitekey="a"></div>
      </div>
      <div id="restore-form-container">
        <div class="g-recaptcha" data-sitekey="b"></div>
      </div>
    </body></html>
    """
    result = detect_challenge(html)
    assert result.detected is False
    assert result.evidence["benign_recaptcha_containers_confirmed"] == [
        "registration-form-container",
        "restore-form-container",
    ]


def test_renamed_container_ids_in_real_manifest_is_detected_as_challenge():
    """Reproduces the exact Codex blocker: the real fixture's `g-recaptcha`
    occurrences sit inside a `<script type="text/x-handlebars-template">`
    block that the DOM never materializes at all — so a DOM-only ancestor
    check cannot tell a genuinely benign container apart from a renamed,
    unapproved one. Only the two known-approved id literals are mutated;
    every other byte of the real fixture is untouched."""
    html = (REGRESSION_FIXTURES / "2hbc3x" / "manifest.html").read_text(encoding="utf-8")

    # 1. sanity: raw HTML genuinely contains the benign widget markers.
    assert "g-recaptcha" in html.lower()

    # 2. sanity: the untouched real fixture is still not a challenge.
    assert detect_challenge(html).detected is False

    # 3-4. rename only the two approved container ids — nothing else.
    mutated = html.replace("registration-form-container", "unapproved-registration-container")
    mutated = mutated.replace("restore-form-container", "unapproved-restore-container")
    assert mutated != html
    assert "registration-form-container" not in mutated
    assert "restore-form-container" not in mutated

    # 5-6. detect_challenge() must now flag it.
    result = detect_challenge(mutated)
    assert result.detected is True
    assert "g-recaptcha" in result.evidence["id_or_class_markers"]

    # 7-8. classify_capture() must route it to CHALLENGE, not ACCEPTED.
    classification = classify_capture(mutated.encode("utf-8"), CaptureKind.SPEC_NAVIGATION)
    assert classification.primary_outcome is ValidationOutcome.CHALLENGE


def test_renamed_container_ids_in_real_group_detail_is_detected_as_challenge():
    """Same reproduction as above, for a real GROUP_DETAIL page — same
    global template, same blocker shape."""
    html = (REGRESSION_FIXTURES / "2hbc3x" / "engine" / "100.html").read_text(encoding="utf-8")
    assert "g-recaptcha" in html.lower()
    assert detect_challenge(html).detected is False

    mutated = html.replace("registration-form-container", "unapproved-registration-container")
    mutated = mutated.replace("restore-form-container", "unapproved-restore-container")

    result = detect_challenge(mutated)
    assert result.detected is True

    classification = classify_capture(mutated.encode("utf-8"), CaptureKind.GROUP_DETAIL)
    assert classification.primary_outcome is ValidationOutcome.CHALLENGE
