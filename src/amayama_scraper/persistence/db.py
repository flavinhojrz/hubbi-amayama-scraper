"""Conexão/transação SQLite — escritor único (research.md §8/§15, DEC-002).

Único módulo (junto com `migrations/`, `repositories/`, `adapters/`,
`blob_store.py`) autorizado a importar `sqlite3` (T198). PostgreSQL não é
projetado nesta feature — apenas a fronteira de repositórios permitiria
uma substituição futura, sem nenhum código de PostgreSQL aqui (DEC-002).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import TypeVar

_T = TypeVar("_T")


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, isolation_level=None)  # autocommit; transactions are explicit
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """BEGIN IMMEDIATE ... COMMIT, com ROLLBACK completo em qualquer exceção.

    Falha nunca deixa estado intermediário visível (data-model.md §13c) —
    escritor único é suficiente para este MVP (research.md §8).
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def run_in_transaction(conn: sqlite3.Connection, fn: Callable[[], _T]) -> _T:
    """Runs `fn()` inside a single BEGIN IMMEDIATE...COMMIT transaction.

    Matches the `Callable[[Callable[[], _T]], _T]` shape expected by
    `snapshots.finalize.finalize_spec_entry()`'s `run_in_transaction`
    parameter (contracts/snapshot-contract.md Fase 2) — the only place
    orchestration/ needs to bind a concrete `conn` to that generic port.
    """
    with transaction(conn):
        return fn()
