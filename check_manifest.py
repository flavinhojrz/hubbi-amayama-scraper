import sqlite3
db = sqlite3.connect('amayama.db')
db.row_factory = sqlite3.Row
row = db.execute("SELECT * FROM spec_group_manifest LIMIT 1;").fetchone()
if row:
    print(dict(row))
else:
    print("No rows found")
