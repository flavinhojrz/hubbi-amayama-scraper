import sqlite3
db = sqlite3.connect('amayama.db')
db.row_factory = sqlite3.Row
print("raw_capture kinds:", [tuple(r) for r in db.execute("SELECT capture_kind, COUNT(*) FROM raw_capture GROUP BY capture_kind").fetchall()])
