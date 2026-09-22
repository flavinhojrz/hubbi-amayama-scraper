"""Monitor leve de progresso para uma CollectionRun em andamento — roda em
outro terminal, só lê o SQLite (modo WAL, seguro ler enquanto o scraper
escreve), sem interferir na execução.

Uso:
    uv run python scripts/watch_repair_progress.py [run_id] [--db amayama.db] [--interval 10]

Sem argumento, usa o run_id do repair atual (60064bc5-f18f-40d1-b15a-db8fcf4f2003).
Ctrl+C para sair.
"""

from __future__ import annotations

import argparse
import sqlite3
import time
from datetime import datetime

DEFAULT_RUN_ID = "60064bc5-f18f-40d1-b15a-db8fcf4f2003"


def snapshot(conn: sqlite3.Connection, run_id: str) -> dict:
    accepted = conn.execute(
        "SELECT COUNT(*) FROM checkpoint_entry WHERE run_id = ? AND status = 'ACCEPTED'",
        (run_id,),
    ).fetchone()[0]
    specs_touched = conn.execute(
        "SELECT COUNT(DISTINCT spec_key) FROM checkpoint_entry WHERE run_id = ?",
        (run_id,),
    ).fetchone()[0]
    challenges_total = conn.execute(
        "SELECT COUNT(*) FROM challenge_event WHERE run_id = ?",
        (run_id,),
    ).fetchone()[0]
    challenges_unresolved = conn.execute(
        "SELECT COUNT(*) FROM challenge_event WHERE run_id = ? AND resolved_at IS NULL",
        (run_id,),
    ).fetchone()[0]
    categories_visited = conn.execute(
        "SELECT COUNT(*) FROM spec_category_visit WHERE run_id = ?",
        (run_id,),
    ).fetchone()[0]
    workers = conn.execute(
        "SELECT worker_id, last_heartbeat_at FROM worker_heartbeat WHERE run_id = ?",
        (run_id,),
    ).fetchall()
    return {
        "accepted": accepted,
        "specs_touched": specs_touched,
        "challenges_total": challenges_total,
        "challenges_unresolved": challenges_unresolved,
        "categories_visited": categories_visited,
        "workers": workers,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_id", nargs="?", default=DEFAULT_RUN_ID)
    parser.add_argument("--db", default="amayama.db")
    parser.add_argument("--interval", type=float, default=10.0)
    args = parser.parse_args()

    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    prev: dict | None = None

    print(f"watching run_id={args.run_id} db={args.db} interval={args.interval}s (Ctrl+C sai)\n")

    try:
        while True:
            now = datetime.now().strftime("%H:%M:%S")
            snap = snapshot(conn, args.run_id)

            if prev is None:
                d_accepted = d_specs = d_challenges = 0
            else:
                d_accepted = snap["accepted"] - prev["accepted"]
                d_specs = snap["specs_touched"] - prev["specs_touched"]
                d_challenges = snap["challenges_total"] - prev["challenges_total"]

            worker_status = ", ".join(
                f"{wid}@{ts[11:19]}" for wid, ts in snap["workers"]
            ) or "nenhum heartbeat"

            print(
                f"[{now}] ACCEPTED={snap['accepted']} (+{d_accepted}) "
                f"specs={snap['specs_touched']} (+{d_specs}) "
                f"categorias={snap['categories_visited']} "
                f"challenges={snap['challenges_total']} (+{d_challenges}, "
                f"{snap['challenges_unresolved']} pendente(s)) "
                f"workers=[{worker_status}]"
            )

            prev = snap
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nparado.")


if __name__ == "__main__":
    main()
