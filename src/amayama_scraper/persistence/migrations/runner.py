"""Runner de migrations — aplica arquivos .sql versionados uma única vez (research.md §8).

Convenção: arquivos nomeados `NNNN_description.sql` neste diretório;
`NNNN` (4 dígitos, zero-padded) é a versão, aplicada em ordem crescente.
Uma migration já aplicada nunca é reaplicada (rastreada em
`schema_migrations`).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent

_CREATE_TRACKING_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
)
"""


def _discover_migrations(migrations_dir: Path) -> list[Path]:
    return sorted(migrations_dir.glob("*.sql"), key=lambda p: p.name)


def _applied_versions(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    return {row["version"] for row in rows}


def run_migrations(conn: sqlite3.Connection, migrations_dir: Path = MIGRATIONS_DIR) -> list[str]:
    """Applies every not-yet-applied .sql file in `migrations_dir`, in order.

    Returns the list of newly-applied migration filenames (empty if
    everything was already applied — idempotent by construction).
    """
    conn.execute(_CREATE_TRACKING_TABLE)
    applied = _applied_versions(conn)

    newly_applied: list[str] = []
    for path in _discover_migrations(migrations_dir):
        if path.name in applied:
            continue
        sql = path.read_text(encoding="utf-8")
        conn.executescript(sql)
        conn.execute(
            "INSERT INTO schema_migrations (version) VALUES (?)",
            (path.name,),
        )
        newly_applied.append(path.name)

    return newly_applied
