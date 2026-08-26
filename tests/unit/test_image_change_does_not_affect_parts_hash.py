"""T128 — mudança só de imagem NÃO altera spec_parts_hash (FR-030, SC-009)."""

from amayama_scraper.domain.hierarchy import Category, Group, Schema
from amayama_scraper.domain.part import Part
from amayama_scraper.fingerprints.image import image_hash
from amayama_scraper.fingerprints.spec import spec_parts_hash


def _tree(image_url: str | None) -> tuple[Category, ...]:
    return (
        Category(
            "engine",
            groups=(
                Group("1", schemas=(Schema("s1", parts=(Part("s1", "A", image_url=image_url),)),)),
            ),
        ),
    )


def test_image_only_change_does_not_affect_spec_parts_hash():
    t1, t2 = _tree("https://x/a.jpg"), _tree("https://x/b.jpg")
    assert spec_parts_hash(t1) == spec_parts_hash(t2)
    assert image_hash(t1) != image_hash(t2)
