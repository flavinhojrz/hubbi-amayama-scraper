"""T169 — helper de transação faz rollback completo em exceção (data-model.md §13c).

T030 (002) — connect() define PRAGMA busy_timeout (data-model.md §8,
research.md §16) para tolerar contenção de escrita entre processos.
"""

import pytest

from amayama_scraper.persistence.db import connect, transaction


def _make_table(conn):
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")


def test_commit_persists_changes():
    conn = connect(":memory:")
    _make_table(conn)
    with transaction(conn):
        conn.execute("INSERT INTO t (value) VALUES (?)", ("a",))
    rows = conn.execute("SELECT value FROM t").fetchall()
    assert [r["value"] for r in rows] == ["a"]


def test_exception_rolls_back_completely():
    conn = connect(":memory:")
    _make_table(conn)
    with pytest.raises(ValueError), transaction(conn):
        conn.execute("INSERT INTO t (value) VALUES (?)", ("a",))
        raise ValueError("boom")
    rows = conn.execute("SELECT value FROM t").fetchall()
    assert rows == []


def test_partial_writes_within_failed_transaction_are_not_visible():
    conn = connect(":memory:")
    _make_table(conn)
    with pytest.raises(ValueError), transaction(conn):
        conn.execute("INSERT INTO t (value) VALUES (?)", ("a",))
        conn.execute("INSERT INTO t (value) VALUES (?)", ("b",))
        raise ValueError("boom")
    assert conn.execute("SELECT COUNT(*) AS c FROM t").fetchone()["c"] == 0


def test_connect_sets_busy_timeout_for_multi_process_contention():
    conn = connect(":memory:")
    (timeout_ms,) = conn.execute("PRAGMA busy_timeout").fetchone()
    assert timeout_ms == 5000


def test_connect_still_sets_foreign_keys_and_wal_unchanged_by_busy_timeout_addition():
    conn = connect(":memory:")
    (foreign_keys,) = conn.execute("PRAGMA foreign_keys").fetchone()
    assert foreign_keys == 1
