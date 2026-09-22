import sqlite3
db = sqlite3.connect('amayama.db')
db.row_factory = sqlite3.Row
print("spec_snapshot columns:", [c[1] for c in db.execute("PRAGMA table_info(spec_snapshot)").fetchall()])
row = db.execute("SELECT counts_json FROM spec_snapshot LIMIT 1;").fetchone()
print("counts_json:", dict(row) if row else "no data")

print("raw_capture count:", db.execute("SELECT COUNT(*) FROM raw_capture").fetchone()[0])
print("raw_capture kinds:", db.execute("SELECT capture_kind, COUNT(*) FROM raw_capture GROUP BY capture_kind").fetchall())
