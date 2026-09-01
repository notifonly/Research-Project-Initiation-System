"""Validate schema.sql by creating SQLite DB and verifying structure."""
import sqlite3
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

db_path = os.path.join(os.path.dirname(__file__), "knowledge.db")
if os.path.exists(db_path):
    os.remove(db_path)

conn = sqlite3.connect(db_path)

with open(os.path.join(os.path.dirname(__file__), "schema.sql"), encoding="utf-8") as f:
    conn.executescript(f.read())
conn.commit()

print(f"SQLite version: {sqlite3.sqlite_version}")

tables = conn.execute(
    "SELECT name, type FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%' ORDER BY type, name"
).fetchall()

current_type = None
for name, typ in tables:
    if typ != current_type:
        current_type = typ
        print(f"\n-- {typ.upper()}S --")
    row = conn.execute(f'SELECT COUNT(*) FROM [{name}]').fetchone()
    print(f"  {name:35s} {row[0]:6d} rows")

# verify FTS
fts_count = conn.execute("SELECT COUNT(*) FROM sources_fts").fetchone()[0]
print(f"\nFTS index: sources_fts ({fts_count} entries)")

size = os.path.getsize(db_path)
print(f"\nDB: {db_path} ({size:,} bytes)")
conn.close()
