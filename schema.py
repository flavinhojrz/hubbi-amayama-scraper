import sqlite3
db = sqlite3.connect('amayama.db')
for row in db.execute('SELECT sql FROM sqlite_master WHERE type IN ("table", "view") AND sql IS NOT NULL;'):
    print(row[0])
