"""T099 — `amayama-scraper run --dry-run` via cli/main.py, transporte nunca
instanciado, produz o plano no stdout sem tocar SQLite/filesystem além de
leitura (DEC-009, SC-014)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from amayama_scraper.checkpoint.collection_run import CollectionRun
from amayama_scraper.cli.main import main
from amayama_scraper.domain.identity import SpecIdentity
from amayama_scraper.domain.manifest import ManifestCategory, ManifestGroupRef, SpecGroupManifest
from amayama_scraper.persistence.db import connect
from amayama_scraper.persistence.migrations.runner import run_migrations
from amayama_scraper.persistence.repositories.checkpoint_repo import save_collection_run
from amayama_scraper.persistence.repositories.manifest_repo import save_manifest
from amayama_scraper.persistence.repositories.spec_registry_repo import save_spec_identity


def _dump_db(db_path: str) -> str:
    conn = connect(db_path)
    lines = []
    tables = [
        r["name"]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
    ]
    for table in tables:
        for row in conn.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall():  # noqa: S608
            lines.append(f"{table}:{dict(row)}")
    conn.close()
    return "\n".join(lines)


def test_dry_run_via_cli_never_instantiates_transport_and_produces_zero_diff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = str(tmp_path / "amayama.db")
    raw_root = tmp_path / "raw"

    conn = connect(db_path)
    run_migrations(conn)
    identity = SpecIdentity(
        source="AMAYAMA",
        manufacturer="VOLKSWAGEN",
        vehicle_model="AMAROK",
        market="AMA-BR",
        model_code="S7BC8A",
        amayama_catalog_id="62184",
        production_period_raw="2022.06 - ...",
        source_url="https://x/62184",
        production_start=date(2022, 6, 1),
    )
    save_spec_identity(conn, identity)
    conn.close()

    def _fail_if_instantiated(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("ChromeCdpTransport must never be instantiated during --dry-run")

    monkeypatch.setattr("amayama_scraper.cli.main.ChromeCdpTransport", _fail_if_instantiated)

    # _dump_db() itself opens a WAL-mode connection (persistence.db.connect())
    # and may leave -wal/-shm sidecars — call it FIRST so that side effect is
    # already settled, then snapshot the directory immediately before/after
    # main() alone, with no other filesystem-touching call in between.
    before_rows = _dump_db(db_path)
    files_before_dry_run = sorted(p.name for p in tmp_path.iterdir())

    exit_code = main(["run", "--dry-run", "--db-path", db_path, "--raw-root", str(raw_root)])

    files_after_dry_run = sorted(p.name for p in tmp_path.iterdir())
    after_rows = _dump_db(db_path)

    assert exit_code == 0
    assert before_rows == after_rows
    # main()'s --dry-run path adds nothing beyond what already existed —
    # persistence.db.connect()'s WAL pragma is deliberately NOT used for
    # --dry-run reads (Blocker 1, Codex).
    assert files_after_dry_run == files_before_dry_run
    assert not raw_root.exists()
    captured = capsys.readouterr()
    assert "discovered specs: 1" in captured.out


def test_dry_run_reports_pending_group_count_when_manifest_already_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from datetime import UTC, datetime

    db_path = str(tmp_path / "amayama.db")
    raw_root = tmp_path / "raw"

    conn = connect(db_path)
    run_migrations(conn)
    identity = SpecIdentity(
        source="AMAYAMA",
        manufacturer="VOLKSWAGEN",
        vehicle_model="AMAROK",
        market="AMA-BR",
        model_code="S7BC8A",
        amayama_catalog_id="62184",
        production_period_raw="2022.06 - ...",
        source_url="https://x/62184",
        production_start=date(2022, 6, 1),
    )
    key = save_spec_identity(conn, identity)
    save_collection_run(conn, CollectionRun(run_id="run-1"))
    save_manifest(
        conn,
        SpecGroupManifest(
            spec_key=key,
            source_capture_id="cap-1",
            discovered_at=datetime.now(UTC),
            categories=(
                ManifestCategory(
                    category_slug="engine",
                    groups=(ManifestGroupRef(group_id="100", source_url="https://x/engine/100"),),
                ),
            ),
            manifest_complete=True,
        ),
        run_id="run-1",
    )
    conn.close()

    monkeypatch.setattr(
        "amayama_scraper.cli.main.ChromeCdpTransport",
        lambda **_kw: (_ for _ in ()).throw(
            AssertionError("must never instantiate during --dry-run")
        ),
    )

    exit_code = main(
        ["run", "--dry-run", "--resume", "run-1", "--db-path", db_path, "--raw-root", str(raw_root)]
    )

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "1 pending group(s)" in captured.out


def test_dry_run_over_empty_temp_dir_creates_absolutely_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Blocker 1 (Codex) — DEC-009: --dry-run sobre um --db-path que ainda
    não existe nunca pode criá-lo, nunca pode criar --raw-root, e não pode
    deixar NENHUM arquivo/diretório novo em disco — nem o .db em si, nem
    sidecars -wal/-shm, nem qualquer outro artefato."""
    db_path = str(tmp_path / "state.db")
    raw_root = tmp_path / "raw"

    def _fail_if_instantiated(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("ChromeCdpTransport must never be instantiated during --dry-run")

    monkeypatch.setattr("amayama_scraper.cli.main.ChromeCdpTransport", _fail_if_instantiated)

    before = sorted(p.name for p in tmp_path.iterdir())
    assert before == []  # sanity: truly empty temp dir

    exit_code = main(["run", "--dry-run", "--db-path", db_path, "--raw-root", str(raw_root)])

    assert exit_code == 0
    assert not Path(db_path).exists()
    assert not raw_root.exists()
    after = sorted(p.name for p in tmp_path.iterdir())
    assert after == []  # absolutely nothing was created anywhere under tmp_path

    captured = capsys.readouterr()
    assert "discovered specs: 0" in captured.out
