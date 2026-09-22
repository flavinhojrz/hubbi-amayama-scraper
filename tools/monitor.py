"""Dashboard de terminal, ao vivo, pra acompanhar runs do scraper.

Lê `amayama.db` direto (read-only, nunca escreve) e mostra, agrupado por
categoria (vehicle_model + market — ex.: GOL GL-BR, AMAROK AMA-BR, e
qualquer modelo novo que passe a ser raspado):

  - Specs:    quantas já chegaram a VALID / total descoberto
  - ACCEPTED: grupos de peças aceitos (deduplicado por spec_key+categoria+
    grupo — reprocessamentos sob run_ids diferentes nunca contam em dobro)
  - REJECTED: grupos AINDA sem nenhum ACCEPTED em run nenhum — uma unidade
    rejeitada num run antigo e aceita depois num run mais novo já não conta
    aqui (mesmo que a linha REJECTED continue no histórico do banco)
  - WORKERS: heartbeat de cada processo worker que já rodou sob essa
    categoria (mais recente primeiro — o(s) do topo com "ATIVO" são os que
    estão rodando agora; os demais são de sessões anteriores)
  - LEASES: leases de spec mais recentes (ATIVO = ainda não expirou)

Uso:
    python tools/monitor.py                    # uma leitura, imprime e sai
    python tools/monitor.py --watch             # atualiza a cada 5s (Ctrl+C sai)
    python tools/monitor.py --watch --interval 10
    python tools/monitor.py --db-path amayama.db
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path

_HEARTBEAT_STALE_SECONDS = 240.0  # mesmo default de WorkerPoolConfig.heartbeat_staleness_seconds
_LEASES_SHOWN_PER_SCOPE = 15


def _has_pending_wal_data(db_path: str) -> bool:
    """Mesma lógica de cli/main.py:_has_pending_wal_data — um `-wal` com
    conteúdo significa que um writer (o scraper rodando agora) já commitou
    dados ainda não levados pro arquivo principal; ignorá-lo mostraria
    estado desatualizado."""
    wal_path = Path(f"{db_path}-wal")
    return wal_path.exists() and wal_path.stat().st_size > 0


def _connect_ro(db_path: str) -> sqlite3.Connection:
    """Mesma lógica de cli/main.py:_connect_read_only — nunca cria/altera
    `-wal`/`-shm`, participa do protocolo de leitura do WAL quando há um
    writer real com dados pendentes."""
    if _has_pending_wal_data(db_path):
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    else:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro&immutable=1", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _now() -> datetime:
    return datetime.now(UTC)


def _parse_ts(raw: str) -> datetime:
    return datetime.fromisoformat(raw)


def _fmt_age(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s atrás"
    if seconds < 3600:
        return f"{seconds / 60:.0f}min atrás"
    return f"{seconds / 3600:.1f}h atrás"


def _run_ids_for_scope(conn: sqlite3.Connection, vehicle_model: str, market: str) -> list[str]:
    rows = conn.execute("SELECT run_id, scope FROM collection_run").fetchall()
    return [r["run_id"] for r in rows if r["scope"].split(":")[-2:] == [vehicle_model, market]]


def render(conn: sqlite3.Connection) -> str:
    now = _now()
    lines: list[str] = []

    scopes = conn.execute(
        "SELECT DISTINCT vehicle_model, market FROM spec_registry ORDER BY vehicle_model, market"
    ).fetchall()

    if not scopes:
        return "(nenhuma spec descoberta ainda neste banco)"

    for scope in scopes:
        vehicle_model, market = scope["vehicle_model"], scope["market"]

        total = conn.execute(
            "SELECT COUNT(*) FROM spec_registry WHERE vehicle_model=? AND market=?",
            (vehicle_model, market),
        ).fetchone()[0]
        valid = conn.execute(
            """
            SELECT COUNT(*) FROM spec_registry sr
            JOIN current_spec_state cs ON cs.spec_identity_ref = sr.stable_key
            WHERE sr.vehicle_model=? AND sr.market=?
            """,
            (vehicle_model, market),
        ).fetchone()[0]
        accepted = conn.execute(
            """
            SELECT COUNT(DISTINCT ce.spec_key || ':' || ce.category_slug || ':' || ce.group_id)
            FROM checkpoint_entry ce
            JOIN spec_registry sr ON sr.stable_key = ce.spec_key
            WHERE ce.status = 'ACCEPTED' AND sr.vehicle_model = ? AND sr.market = ?
            """,
            (vehicle_model, market),
        ).fetchone()[0]
        # "Ainda quebrado" = REJECTED sem NENHUM ACCEPTED depois, em run
        # nenhum, pra essa mesma (spec_key, categoria, grupo) — uma unidade
        # rejeitada num run antigo e aceita com sucesso num run mais novo
        # não é mais um problema real, mesmo que a linha REJECTED continue
        # no histórico (checkpoint_entry nunca é apagado/reescrito).
        rejected = conn.execute(
            """
            SELECT COUNT(DISTINCT ce.spec_key || ':' || ce.category_slug || ':' || ce.group_id)
            FROM checkpoint_entry ce
            JOIN spec_registry sr ON sr.stable_key = ce.spec_key
            WHERE ce.status = 'REJECTED' AND sr.vehicle_model = ? AND sr.market = ?
              AND NOT EXISTS (
                  SELECT 1 FROM checkpoint_entry ce2
                  WHERE ce2.spec_key = ce.spec_key
                    AND ce2.category_slug = ce.category_slug
                    AND ce2.group_id = ce.group_id
                    AND ce2.status = 'ACCEPTED'
              )
            """,
            (vehicle_model, market),
        ).fetchone()[0]

        lines.append(f"=== {vehicle_model} {market} ===")
        lines.append(f"Specs:    {valid} / {total}")
        lines.append(f"ACCEPTED: {accepted}")
        lines.append(f"REJECTED: {rejected}")

        run_ids = _run_ids_for_scope(conn, vehicle_model, market)
        if run_ids:
            placeholders = ",".join("?" * len(run_ids))

            workers = conn.execute(
                f"""
                SELECT worker_id, pid, last_heartbeat_at FROM worker_heartbeat
                WHERE run_id IN ({placeholders})
                ORDER BY last_heartbeat_at DESC
                """,  # noqa: S608 - placeholders são só "?", nunca interpolação de dado
                run_ids,
            ).fetchall()
            if workers:
                lines.append("")
                lines.append("--- WORKERS ---")
                for w in workers:
                    parts = w["worker_id"].split(":")
                    worker_index = parts[-2] if len(parts) >= 2 else "?"
                    age = (now - _parse_ts(w["last_heartbeat_at"])).total_seconds()
                    status = "ATIVO " if age < _HEARTBEAT_STALE_SECONDS else "parado"
                    lines.append(
                        f"{status} | worker {worker_index} | PID {w['pid']:<7} | "
                        f"{w['last_heartbeat_at']} ({_fmt_age(age)})"
                    )

            leases = conn.execute(
                f"""
                SELECT spec_key, owner, expires_at, renewed_at FROM spec_lease
                WHERE run_id IN ({placeholders})
                ORDER BY renewed_at DESC
                LIMIT {_LEASES_SHOWN_PER_SCOPE}
                """,  # noqa: S608 - placeholders são só "?", nunca interpolação de dado
                run_ids,
            ).fetchall()
            if leases:
                lines.append("")
                lines.append(f"--- LEASES ({len(leases)} mais recentes) ---")
                for lease in leases:
                    active = _parse_ts(lease["expires_at"]) > now
                    owner_parts = lease["owner"].split(":")
                    worker_index = owner_parts[-2] if len(owner_parts) >= 2 else lease["owner"]
                    status = "ATIVO " if active else "antigo"
                    lines.append(
                        f"{status} | worker {worker_index} | spec {lease['spec_key'][:12]}"
                    )

        lines.append("")

    return "\n".join(lines).rstrip("\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--db-path", default="amayama.db")
    parser.add_argument("--watch", action="store_true", help="atualiza continuamente até Ctrl+C")
    parser.add_argument("--interval", type=float, default=5.0, metavar="SECONDS")
    args = parser.parse_args()

    if not args.watch:
        conn = _connect_ro(args.db_path)
        try:
            print(render(conn))
        finally:
            conn.close()
        return 0

    try:
        while True:
            conn = _connect_ro(args.db_path)
            try:
                output = render(conn)
            finally:
                conn.close()
            os.system("cls" if os.name == "nt" else "clear")
            header = (
                f"[{_now().isoformat()}] {args.db_path} — "
                f"atualiza a cada {args.interval:.0f}s (Ctrl+C sai)\n"
            )
            print(header)
            print(output)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
