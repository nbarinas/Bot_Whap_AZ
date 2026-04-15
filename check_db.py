import sqlite3
import os

# Correct path - inside backend/ folder
db_path = os.path.join(os.path.dirname(__file__), 'bot_data.db')
print(f"DB path: {db_path}")
print(f"Exists: {os.path.exists(db_path)}")

conn = sqlite3.connect(db_path)
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print("Tables:", tables)

if any('bot_quotas' in t[0] for t in tables):
    cols = conn.execute("PRAGMA table_info(bot_quotas)").fetchall()
    print("bot_quotas columns:", [c[1] for c in cols])

conn.close()
