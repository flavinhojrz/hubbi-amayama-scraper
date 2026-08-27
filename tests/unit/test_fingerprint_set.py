"""T038 — FingerprintSet: 4 independent hashes + version (data-model.md §7)."""

import pytest

from amayama_scraper.fingerprints.types import FingerprintSet


def make_set(**overrides: object) -> FingerprintSet:
    defaults: dict[str, object] = dict(
        structure_hash="a" * 64,
        spec_parts_hash="b" * 64,
        schema_semantic_hash="c" * 64,
        image_hash="d" * 64,
        fingerprint_version="amayama-fingerprint-v1",
    )
    defaults.update(overrides)
    return FingerprintSet(**defaults)  # type: ignore[arg-type]


def test_fields_independent():
    fp = make_set()
    assert fp.structure_hash != fp.spec_parts_hash != fp.schema_semantic_hash != fp.image_hash


@pytest.mark.parametrize(
    "field_name",
    [
        "structure_hash",
        "spec_parts_hash",
        "schema_semantic_hash",
        "image_hash",
        "fingerprint_version",
    ],
)
def test_required_fields_cannot_be_empty(field_name: str) -> None:
    with pytest.raises(ValueError):
        make_set(**{field_name: ""})
