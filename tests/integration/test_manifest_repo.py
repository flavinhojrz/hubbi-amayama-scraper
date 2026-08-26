"""T177 — manifest_repo persiste/recupera SpecGroupManifest; get_authoritative() aplica as
condições de autoridade (data-model.md §15).

Condição 1 ("captura de origem ACCEPTED") é estruturalmente garantida pelo
pipeline (T093) — nunca existe um SpecGroupManifest construído a partir de
uma captura rejeitada, então não há cenário de repositório para testá-la
diretamente; ela já está coberta em
tests/integration/test_parser_never_reached_on_rejected_capture.py.
"""

import json
from datetime import UTC, datetime

import pytest

from amayama_scraper.domain.hierarchy import DuplicateGroupIdError
from amayama_scraper.domain.manifest import ManifestCategory, ManifestGroupRef, SpecGroupManifest
from amayama_scraper.persistence.db import connect
from amayama_scraper.persistence.migrations.runner import run_migrations
from amayama_scraper.persistence.repositories.manifest_repo import get_authoritative, save_manifest


def _conn():
    conn = connect(":memory:")
    run_migrations(conn)
    return conn


def _manifest(**overrides: object) -> SpecGroupManifest:
    defaults: dict[str, object] = dict(
        spec_key="spec-1",
        source_capture_id="cap-1",
        discovered_at=datetime(2026, 8, 26, tzinfo=UTC),
        categories=(
            ManifestCategory(
                category_slug="front-axle-steering",
                groups=(ManifestGroupRef(group_id="407", source_url="https://x/407"),),
            ),
        ),
        manifest_complete=True,
    )
    defaults.update(overrides)
    return SpecGroupManifest(**defaults)  # type: ignore[arg-type]


def test_save_and_get_authoritative_round_trips():
    conn = _conn()
    manifest = _manifest()
    save_manifest(conn, manifest, run_id="run-1")

    fetched = get_authoritative(conn, "spec-1", "run-1")
    assert fetched is not None
    assert fetched.manifest_complete is True
    assert fetched.categories == manifest.categories


def test_manifest_complete_false_is_not_authoritative():
    conn = _conn()
    save_manifest(conn, _manifest(manifest_complete=False), run_id="run-1")
    assert get_authoritative(conn, "spec-1", "run-1") is None


def test_missing_manifest_returns_none():
    conn = _conn()
    assert get_authoritative(conn, "spec-unknown", "run-unknown") is None


def test_different_run_id_does_not_match():
    conn = _conn()
    save_manifest(conn, _manifest(), run_id="run-1")
    assert get_authoritative(conn, "spec-1", "run-2") is None


def test_corrupted_persisted_duplicate_group_raises_rather_than_silently_authoritative():
    conn = _conn()
    corrupted_categories = json.dumps(
        [
            {
                "category_slug": "front-axle-steering",
                "groups": [
                    {"group_id": "407", "source_url": "https://x/407"},
                    {"group_id": "407", "source_url": "https://x/407-dup"},
                ],
            }
        ]
    )
    conn.execute(
        """
        INSERT INTO spec_group_manifest (
            spec_key, run_id, source_capture_id, discovered_at,
            categories_json, manifest_complete, validation_evidence_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        ("spec-1", "run-1", "cap-1", "2026-08-26T00:00:00+00:00", corrupted_categories, 1, "{}"),
    )
    with pytest.raises(DuplicateGroupIdError):
        get_authoritative(conn, "spec-1", "run-1")
