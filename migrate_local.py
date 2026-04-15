import sqlite3
import os

db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend', 'bot_data.db')
print(f"DB: {db_path}")

conn = sqlite3.connect(db_path)

# Check current columns
cols = [c[1] for c in conn.execute("PRAGMA table_info(bot_quotas)").fetchall()]
print("Current columns:", cols)

migrations = [
    "ALTER TABLE bot_quotas ADD COLUMN study_type VARCHAR DEFAULT 'STANDARD'",
    "ALTER TABLE bot_quotas ADD COLUMN store_id INTEGER",
    "ALTER TABLE bot_quotas ADD COLUMN planned_supervisor VARCHAR",
    "ALTER TABLE bot_quotas ADD COLUMN planned_interviewer VARCHAR",
    "ALTER TABLE quota_submissions ADD COLUMN supervisor_name VARCHAR",
    "ALTER TABLE quota_submissions ADD COLUMN visit_date VARCHAR",
]

for sql in migrations:
    try:
        conn.execute(sql)
        print("OK:", sql[:60])
    except Exception as e:
        print("Skip:", e)

conn.commit()

# Confirm
cols2 = [c[1] for c in conn.execute("PRAGMA table_info(bot_quotas)").fetchall()]
print("New columns:", cols2)
conn.close()
print("Done.")
