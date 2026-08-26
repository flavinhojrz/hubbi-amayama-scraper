"""T114 — part_fingerprint(): determinismo, domain separator, campos canônicos, pr_codes."""

from amayama_scraper.domain.part import Part
from amayama_scraper.fingerprints.canonical import domain_hash
from amayama_scraper.fingerprints.part import part_fingerprint


def _part(**overrides: object) -> Part:
    defaults: dict[str, object] = dict(
        schema_id="407",
        position_pnc="A01",
        oem_code="1K0407151",
        description="Control arm",
        details="left side",
        period_application_text="08.2010-12.2015",
        pr_codes=("PX1",),
        quantity="1",
        image_url="https://x/img.jpg",
    )
    defaults.update(overrides)
    return Part(**defaults)  # type: ignore[arg-type]


def test_deterministic():
    p = _part()
    assert part_fingerprint(p) == part_fingerprint(p)


def test_matches_domain_hash_formula():
    p = _part()
    expected = domain_hash(
        "amayama:part:v1\0",
        {
            "schema_id": "407",
            "pnc": "A01",
            "oem": "1K0407151",
            "description": "Control arm",
            "details": "left side",
            "period": "08.2010-12.2015",
            "required": "1",
        },
    )
    assert part_fingerprint(p) == expected


def test_pr_codes_excluded_from_fingerprint():
    p1 = _part(pr_codes=("PX1",))
    p2 = _part(pr_codes=("PJ1", "1BA"))
    assert part_fingerprint(p1) == part_fingerprint(p2)


def test_image_url_excluded_from_fingerprint():
    p1 = _part(image_url="https://x/a.jpg")
    p2 = _part(image_url="https://x/b.jpg")
    assert part_fingerprint(p1) == part_fingerprint(p2)


def test_different_oem_changes_fingerprint():
    p1 = _part(oem_code="A")
    p2 = _part(oem_code="B")
    assert part_fingerprint(p1) != part_fingerprint(p2)


def test_normalizes_before_hashing_raw_and_clean_inputs_match():
    raw = _part(oem_code="1K0 407 151", description="  Control  arm  ")
    clean = _part(oem_code="1K0407151", description="Control arm")
    assert part_fingerprint(raw) == part_fingerprint(clean)
