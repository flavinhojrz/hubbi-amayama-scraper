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
from pathlib import Path
from typing import TypeVar

_T = TypeVar("_T")


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, isolation_level=None)  # autocommit; transactions are explicit
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    # T030/T031 (002) — tolera contenção de escrita entre processos (research.md
    # §16): sem isto, um segundo processo escrevendo durante uma transação de
    # outro falha imediatamente com "database is locked" em vez de esperar.
    # Comportamento single-process é idêntico ao anterior (nunca há contenção
    # a esperar).
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def _has_pending_wal_data(db_path: str) -> bool:
    """True quando `<db_path>-wal` existe e tem conteúdo — há commits ainda não
    checkpontados feitos por um writer com a conexão aberta (mesma lógica
    documentada em cli/main.py::_has_pending_wal_data para --dry-run;
    003-corpus-analysis-tool precisa da mesma garantia para connect_read_only,
    reimplementada aqui como função pública de persistence/db.py em vez de
    duplicar a lógica dentro de cli/analyze.py)."""
    wal_path = Path(f"{db_path}-wal")
    return wal_path.exists() and wal_path.stat().st_size > 0


def connect_read_only(db_path: str) -> sqlite3.Connection:
    """Conexão genuinamente somente-leitura — nunca cria o arquivo, nunca
    escreve, nunca cria `-wal`/`-shm` como efeito colateral. O chamador deve
    verificar `Path(db_path).exists()` antes de chamar esta função; abrir
    `mode=ro` sobre um arquivo inexistente levanta `sqlite3.OperationalError`.

    Duas estratégias, escolhidas dinamicamente (mesma técnica de
    cli/main.py::_connect_read_only): sem WAL pendente, `mode=ro&immutable=1`
    (evita side-effects); com WAL pendente (writer legítimo ainda aberto),
    `mode=ro` puro (participa do protocolo de leitura do WAL sem criar nada
    novo nem esconder dados já commitados apenas no WAL).
    """
    if _has_pending_wal_data(db_path):
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    else:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro&immutable=1", uri=True)
    conn.row_factory = sqlite3.Row
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
