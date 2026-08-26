"""T181 — FilesystemRawBlobStore + SqliteRawCaptureRepository via accept_capture()
(Phase 3), sem alteração em ingestion/: dedup físico, observações distintas, e
replay determinístico simulando restart do processo.
"""

from datetime import UTC, datetime
from pathlib import Path

from amayama_scraper.ingestion.accept import accept_capture
from amayama_scraper.ingestion.capture_input import RawCaptureInput
from amayama_scraper.ingestion.capture_kind import CaptureKind
from amayama_scraper.ingestion.ports import reconstruct_raw_content
from amayama_scraper.persistence.adapters.filesystem_raw_blob_store import FilesystemRawBlobStore
from amayama_scraper.persistence.adapters.sqlite_raw_capture_repository import (
    SqliteRawCaptureRepository,
)
from amayama_scraper.persistence.db import connect
from amayama_scraper.persistence.migrations.runner import run_migrations


def _setup(tmp_path: Path):
    conn = connect(str(tmp_path / "db.sqlite3"))
    run_migrations(conn)
    blob_store = FilesystemRawBlobStore(tmp_path / "blobs", conn)
    capture_repo = SqliteRawCaptureRepository(conn)
    return conn, blob_store, capture_repo


def _input(raw_content: bytes, **overrides: object) -> RawCaptureInput:
    defaults: dict[str, object] = dict(
        capture_kind=CaptureKind.GROUP_DETAIL,
        source_url="https://www.amayama.com/en/x/407",
        collected_at=datetime.now(UTC),
        raw_content=raw_content,
        run_id="run-1",
    )
    defaults.update(overrides)
    return RawCaptureInput(**defaults)  # type: ignore[arg-type]


def test_dedup_physical_blob_distinct_observations(tmp_path: Path):
    conn, blob_store, capture_repo = _setup(tmp_path)
    content = b"<html>same content</html>"

    capture_a = accept_capture(_input(content), blob_store, capture_repo)
    capture_b = accept_capture(_input(content), blob_store, capture_repo)

    assert capture_a.capture_id != capture_b.capture_id  # distinct observations
    assert capture_a.content_hash == capture_b.content_hash  # same physical content

    blob_rows = conn.execute("SELECT COUNT(*) AS c FROM raw_blob").fetchone()
    assert blob_rows["c"] == 1  # deduplicated physically

    capture_rows = conn.execute("SELECT COUNT(*) AS c FROM raw_capture").fetchone()
    assert capture_rows["c"] == 2  # never collapsed as observations


def test_replay_reconstructs_raw_content_from_a_fresh_instance_simulating_restart(
    tmp_path: Path,
):
    conn, blob_store, capture_repo = _setup(tmp_path)
    content = b"<html>group detail page</html>"
    accepted = accept_capture(_input(content), blob_store, capture_repo)
    conn.close()

    # simulate a process restart: brand-new connection + brand-new adapter instances
    fresh_conn = connect(str(tmp_path / "db.sqlite3"))
    fresh_blob_store = FilesystemRawBlobStore(tmp_path / "blobs", fresh_conn)
    fresh_capture_repo = SqliteRawCaptureRepository(fresh_conn)

    reconstructed = reconstruct_raw_content(
        accepted.capture_id, fresh_capture_repo, fresh_blob_store
    )
    assert reconstructed == content


def test_get_missing_capture_returns_none(tmp_path: Path):
    _, _, capture_repo = _setup(tmp_path)
    assert capture_repo.get("nonexistent") is None
