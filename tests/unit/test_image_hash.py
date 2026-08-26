"""T126 — image_hash(): multiset de imagens próprias, independente de spec_parts_hash."""

from amayama_scraper.domain.hierarchy import Category, Group, Schema
from amayama_scraper.domain.part import Part
from amayama_scraper.fingerprints.image import image_hash


def _tree(image_url: str | None) -> tuple[Category, ...]:
    return (
        Category(
            "engine",
            groups=(
                Group(
                    "1",
                    schemas=(Schema("s1", parts=(Part("s1", "A", image_url=image_url),)),),
                ),
            ),
        ),
    )


def test_different_image_changes_hash():
    assert image_hash(_tree("https://x/a.jpg")) != image_hash(_tree("https://x/b.jpg"))


def test_no_image_produces_empty_multiset_hash():
    assert image_hash(_tree(None)) == image_hash(_tree(None))


def test_deterministic():
    t = _tree("https://x/a.jpg")
    assert image_hash(t) == image_hash(t)
