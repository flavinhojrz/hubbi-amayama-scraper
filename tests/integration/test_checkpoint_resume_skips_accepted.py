"""T204 — get_pending_groups() deriva o universo esperado do manifesto autoritativo
e nunca reprocessa ACCEPTED (FR-012, SC-004)."""

from datetime import UTC, datetime

import pytest

from amayama_scraper.checkpoint.checkpoint_entry import CheckpointEvent
from amayama_scraper.checkpoint.collection_run import CollectionRun
from amayama_scraper.checkpoint.resume import NoAuthoritativeManifestError, get_pending_groups
from amayama_scraper.checkpoint.upsert import upsert_checkpoint
from amayama_scraper.domain.manifest import ManifestCategory, ManifestGroupRef, SpecGroupManifest
from amayama_scraper.persistence.db import connect
from amayama_scraper.persistence.migrations.runner import run_migrations
from amayama_scraper.persistence.repositories.checkpoint_repo import save_collection_run
from amayama_scraper.persistence.repositories.manifest_repo import save_manifest


def _conn():
    conn = connect(":memory:")
    run_migrations(conn)
    save_collection_run(conn, CollectionRun(run_id="run-1"))
    conn.execute(
        "INSERT INTO raw_blob (content_hash, size_bytes, storage_path, first_seen_at) "
        "VALUES (?, ?, ?, ?)",
        ("x" * 64, 10, "/blobs/x", "2026-08-26T00:00:00+00:00"),
    )
    for cap_id in ("cap-407", "cap-409"):
        conn.execute(
            "INSERT INTO raw_capture (capture_id, run_id, content_hash, source_url, "
            "collected_at, capture_kind, acquisition_mode) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                cap_id,
                "run-1",
                "x" * 64,
                f"https://x/{cap_id}",
                "2026-08-26T00:00:00+00:00",
                "GROUP_DETAIL",
                "MANUAL_BROWSER",
            ),
        )
    manifest = SpecGroupManifest(
        spec_key="spec-1",
        source_capture_id="cap-manifest",
        discovered_at=datetime(2026, 8, 26, tzinfo=UTC),
        categories=(
            ManifestCategory(
                category_slug="front-axle-steering",
                groups=(
                    ManifestGroupRef(group_id="407", source_url="https://x/407"),
                    ManifestGroupRef(group_id="409", source_url="https://x/409"),
                ),
            ),
        ),
        manifest_complete=True,
    )
    save_manifest(conn, manifest, run_id="run-1")
    return conn


def test_pending_groups_excludes_accepted():
    conn = _conn()
    upsert_checkpoint(
        conn,
        run_id="run-1",
        spec_key="spec-1",
        category_slug="front-axle-steering",
        group_id="407",
        event=CheckpointEvent.START_ATTEMPT,
    )
    upsert_checkpoint(
        conn,
        run_id="run-1",
        spec_key="spec-1",
        category_slug="front-axle-steering",
        group_id="407",
        event=CheckpointEvent.ACCEPT,
        raw_capture_id="cap-407",
    )

    pending = get_pending_groups(conn, "run-1", "spec-1")
    assert pending == [("front-axle-steering", "409")]


def test_never_attempted_group_counts_as_pending():
    conn = _conn()
    pending = get_pending_groups(conn, "run-1", "spec-1")
    assert set(pending) == {("front-axle-steering", "407"), ("front-axle-steering", "409")}


def test_no_authoritative_manifest_raises():
    conn = connect(":memory:")
    run_migrations(conn)
    save_collection_run(conn, CollectionRun(run_id="run-1"))
    with pytest.raises(NoAuthoritativeManifestError):
        get_pending_groups(conn, "run-1", "spec-unknown")
