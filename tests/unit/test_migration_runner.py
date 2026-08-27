"""T171 — runner aplica migrations em ordem e nunca reaplica uma já aplicada."""

from pathlib import Path

from amayama_scraper.persistence.db import connect
from amayama_scraper.persistence.migrations.runner import run_migrations


def _write_migrations(tmp_path: Path) -> Path:
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()
    (migrations_dir / "0001_a.sql").write_text("CREATE TABLE a (id INTEGER PRIMARY KEY);")
    (migrations_dir / "0002_b.sql").write_text(
        "CREATE TABLE b (id INTEGER PRIMARY KEY, a_id INTEGER);"
    )
    return migrations_dir


def test_applies_all_migrations_in_order(tmp_path: Path):
    migrations_dir = _write_migrations(tmp_path)
    conn = connect(":memory:")
    applied = run_migrations(conn, migrations_dir)
    assert applied == ["0001_a.sql", "0002_b.sql"]

    tables = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    assert {"a", "b", "schema_migrations"} <= tables


def test_never_reapplies_an_already_applied_migration(tmp_path: Path):
    migrations_dir = _write_migrations(tmp_path)
    conn = connect(":memory:")
    first_run = run_migrations(conn, migrations_dir)
    assert first_run == ["0001_a.sql", "0002_b.sql"]

    second_run = run_migrations(conn, migrations_dir)
    assert second_run == []


def test_applies_only_new_migration_added_later(tmp_path: Path):
    migrations_dir = _write_migrations(tmp_path)
    conn = connect(":memory:")
    run_migrations(conn, migrations_dir)

    (migrations_dir / "0003_c.sql").write_text("CREATE TABLE c (id INTEGER PRIMARY KEY);")
    third_run = run_migrations(conn, migrations_dir)
    assert third_run == ["0003_c.sql"]
