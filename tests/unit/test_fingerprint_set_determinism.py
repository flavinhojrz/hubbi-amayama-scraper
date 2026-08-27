"""T131 — compute_fingerprint_set(): determinismo ponta-a-ponta (US3, Acceptance Scenario 1)."""

from amayama_scraper.domain.hierarchy import Category, Group, Schema
from amayama_scraper.domain.part import Part
from amayama_scraper.fingerprints.version import FINGERPRINT_VERSION, compute_fingerprint_set


def _tree() -> tuple[Category, ...]:
    return (
        Category(
            "engine",
            groups=(
                Group(
                    "010",
                    schemas=(
                        Schema(
                            "s1",
                            parts=(Part("s1", "A01", oem_code="1K0407151"),),
                        ),
                    ),
                ),
            ),
        ),
    )


def test_same_input_twice_produces_identical_fingerprint_set():
    tree = _tree()
    assert compute_fingerprint_set(tree) == compute_fingerprint_set(tree)


def test_fingerprint_version_is_the_documented_string():
    result = compute_fingerprint_set(_tree())
    assert result.fingerprint_version == FINGERPRINT_VERSION == "amayama-fingerprint-v1"
