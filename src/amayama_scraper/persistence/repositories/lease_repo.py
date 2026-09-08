"""lease_repo.py — claim/lease atômico sobre `spec_lease` (005, US2; data-model.md §1).

Todas as funções aqui são declarações SQL simples (autocommit,
`isolation_level=None` — persistence/db.py) — nenhuma abre sua própria
transação `BEGIN IMMEDIATE`, para que possam compor dentro da transação
maior de `orchestration/worker_pool.py::next_claimable_spec()`
(contracts/worker-pool-contract.md §3) sem aninhar `BEGIN`. Chamadas
isoladas (ex.: `renew_lease()` durante o processamento de uma spec, fora de
`next_claimable_spec()`) continuam corretas/atômicas sozinhas: cada
declaração é uma transação implícita própria em modo autocommit.

`try_claim()` é seguro mesmo sem `transaction()` explícito ao redor: a
cláusula `WHERE` do `DO UPDATE` garante que, uma vez que o UPSERT desta
chamada seja commitado com `owner` == o nosso, nenhuma outra escrita pode
"roubar" a posse antes da leitura de confirmação seguinte — só haveria uma
janela de disputa se outro processo pudesse simultaneamente satisfazer
`expires_at <= now`, o que é impossível imediatamente após termos acabado de
escrever um `expires_at` no futuro.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta


def try_claim(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    spec_key: str,
    owner: str,
    now: datetime,
    lease_seconds: float,
) -> int | None:
    """FR-020 a FR-023 (US2): concede o lease a `owner` se, e somente se,
    nenhum outro dono detém um lease não expirado para `(run_id, spec_key)`
    — cobre os três casos em uma única declaração condicional (data-model.md
    §1): primeira reivindicação (nenhuma linha ainda), renovação pelo mesmo
    dono, e recovery de um lease expirado (dono anterior morto/travado).

    Retorna o `lease_token` (005 hardening, BLOCKER 1 — fencing) atribuído a
    esta chamada quando `owner` efetivamente detém o lease após ela (nunca
    `0`/falso — sempre >= 1); `None` quando o claim falhou. `lease_token`
    incrementa a cada claim bem-sucedido (primeira reivindicação, renovação
    OU takeover) — nunca reutilizado, garantindo que qualquer referência a um
    token anterior fique estruturalmente obsoleta assim que uma nova posse
    (mesmo pelo mesmo dono) é estabelecida."""
    now_iso = now.isoformat()
    expires_at_iso = (now + timedelta(seconds=lease_seconds)).isoformat()
    conn.execute(
        """
        INSERT INTO spec_lease
            (run_id, spec_key, owner, lease_token, acquired_at, renewed_at, expires_at)
        VALUES (?, ?, ?, 1, ?, ?, ?)
        ON CONFLICT (run_id, spec_key) DO UPDATE SET
            owner = excluded.owner,
            lease_token = spec_lease.lease_token + 1,
            acquired_at = excluded.acquired_at,
            renewed_at = excluded.renewed_at,
            expires_at = excluded.expires_at
        WHERE spec_lease.owner = excluded.owner OR spec_lease.expires_at <= ?
        """,
        (run_id, spec_key, owner, now_iso, now_iso, expires_at_iso, now_iso),
    )
    row = conn.execute(
        "SELECT owner, lease_token FROM spec_lease WHERE run_id = ? AND spec_key = ?",
        (run_id, spec_key),
    ).fetchone()
    if row is None or row["owner"] != owner:
        return None
    return int(row["lease_token"])


def renew_lease(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    spec_key: str,
    owner: str,
    now: datetime,
    lease_seconds: float,
) -> int | None:
    """FR-022: renova `renewed_at`/`expires_at` — só afeta a linha quando
    `owner` ainda é o dono real (nunca renova um lease que já foi
    reclamado/expirado sob outro dono).

    Retorna o novo `lease_token` (005 hardening, BLOCKER 1) quando a
    renovação foi aplicada; `None` quando `owner` não detém mais o lease
    (outro worker já fez takeover) — o chamador (worker_pool.py) trata
    `None` como sinal para interromper imediatamente o processamento desta
    spec (nunca continuar gravando sob um lease que não é mais seu)."""
    now_iso = now.isoformat()
    expires_at_iso = (now + timedelta(seconds=lease_seconds)).isoformat()
    cursor = conn.execute(
        """
        UPDATE spec_lease SET renewed_at = ?, expires_at = ?, lease_token = lease_token + 1
        WHERE run_id = ? AND spec_key = ? AND owner = ?
        """,
        (now_iso, expires_at_iso, run_id, spec_key, owner),
    )
    if cursor.rowcount == 0:
        return None
    row = conn.execute(
        "SELECT lease_token FROM spec_lease WHERE run_id = ? AND spec_key = ?", (run_id, spec_key)
    ).fetchone()
    return int(row["lease_token"]) if row is not None else None


def release_lease(
    conn: sqlite3.Connection, *, run_id: str, spec_key: str, owner: str, now: datetime
) -> bool:
    """FR-025: libera explicitamente — nunca `DELETE` (data-model.md §1,
    auditabilidade Constitution §4): marca `expires_at` como já expirado
    (`now`), tornando a spec imediatamente reclamável por qualquer worker,
    sem apagar o histórico de quem a deteve por último. Só afeta a linha
    quando `owner` ainda é o dono real."""
    now_iso = now.isoformat()
    cursor = conn.execute(
        "UPDATE spec_lease SET expires_at = ? WHERE run_id = ? AND spec_key = ? AND owner = ?",
        (now_iso, run_id, spec_key, owner),
    )
    return cursor.rowcount > 0


def count_active_leases(conn: sqlite3.Connection, *, run_id: str, now: datetime) -> int:
    """FR-062: leases com `expires_at` estritamente no futuro — usado pelo
    orquestrador para decidir se um novo claim é permitido nesta chamada."""
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM spec_lease WHERE run_id = ? AND expires_at > ?",
        (run_id, now.isoformat()),
    ).fetchone()
    return int(row["n"])


def get_lease_owner(conn: sqlite3.Connection, *, run_id: str, spec_key: str) -> str | None:
    """Leitura auxiliar (diagnóstico/testes) — não participa de nenhuma decisão de claim."""
    row = conn.execute(
        "SELECT owner FROM spec_lease WHERE run_id = ? AND spec_key = ?", (run_id, spec_key)
    ).fetchone()
    return row["owner"] if row is not None else None


def get_lease_token(
    conn: sqlite3.Connection, *, run_id: str, spec_key: str
) -> tuple[str, int] | None:
    """005 hardening (BLOCKER 1 — fencing): `(owner, lease_token)` atuais —
    a checagem de fencing (`orchestration/worker_pool.py`) compara o PAR
    inteiro contra o que o worker capturou no claim/última renovação, nunca
    apenas `owner`."""
    row = conn.execute(
        "SELECT owner, lease_token FROM spec_lease WHERE run_id = ? AND spec_key = ?",
        (run_id, spec_key),
    ).fetchone()
    if row is None:
        return None
    return (row["owner"], int(row["lease_token"]))


def list_active_lease_spec_keys(
    conn: sqlite3.Connection, *, run_id: str, now: datetime
) -> set[str]:
    """`spec_key`s com lease não expirado, INDEPENDENTE do dono — usado por
    `next_claimable_spec()` para: (a) admissão (quantos slots ocupados
    agora) e (b) excluir da lista de candidatos qualquer spec já
    ativamente leased em tempo real por outro worker. Terminalidade e
    elegibilidade após uma passagem sem progresso são decididas por
    `spec_pool_disposition_repo.py` (005 hardening, BLOCKER 2 — 2ª rodada),
    nunca por tempo de expiração de lease."""
    rows = conn.execute(
        "SELECT spec_key FROM spec_lease WHERE run_id = ? AND expires_at > ?",
        (run_id, now.isoformat()),
    ).fetchall()
    return {row["spec_key"] for row in rows}


__all__ = [
    "count_active_leases",
    "get_lease_owner",
    "get_lease_token",
    "list_active_lease_spec_keys",
    "release_lease",
    "renew_lease",
    "try_claim",
]
