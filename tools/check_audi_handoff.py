from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


path = sys.argv[1] if len(sys.argv) > 1 else "audi_mass.db"
backup_path = sys.argv[2] if len(sys.argv) > 2 else None
conn = sqlite3.connect(path)
try:
    print("integrity_check:", conn.execute("PRAGMA integrity_check").fetchone()[0])
    print("foreign_key_check:", conn.execute("PRAGMA foreign_key_check").fetchall())
    print("runs:", conn.execute(
        "SELECT COUNT(*), SUM(completed_at IS NOT NULL) FROM collection_run"
    ).fetchone())
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )]
    print("tables:", tables)
    print("valid_specs:", conn.execute("SELECT COUNT(*) FROM current_spec_state").fetchone()[0])
    print("checkpoint_status:", conn.execute(
        "SELECT status, COUNT(*) FROM checkpoint_entry GROUP BY status ORDER BY status"
    ).fetchall())
    print("unresolved_rejected:", conn.execute(
        "SELECT COUNT(*) FROM checkpoint_entry r "
        "WHERE r.status='REJECTED' AND NOT EXISTS ("
        "SELECT 1 FROM checkpoint_entry a WHERE a.status='ACCEPTED' "
        "AND a.spec_key=r.spec_key AND a.category_slug=r.category_slug "
        "AND a.group_id=r.group_id)"
    ).fetchone()[0])
    print("complete_scopes:", conn.execute(
        "SELECT scope FROM collection_run WHERE completed_at IS NOT NULL ORDER BY scope"
    ).fetchall())
    print("pending_scopes:", conn.execute(
        "SELECT scope FROM collection_run WHERE completed_at IS NULL ORDER BY scope"
    ).fetchall())
    if backup_path:
        dest = sqlite3.connect(backup_path)
        try:
            conn.backup(dest)
        finally:
            dest.close()
        print("backup:", Path(backup_path).resolve())
finally:
    conn.close()
