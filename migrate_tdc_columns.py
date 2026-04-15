"""
Migration script: Add new TDC columns to bot_quotas table in PostgreSQL.
Run this once on Render or any production environment.
"""
import os
import sys

# Try to use the production DB URL
db_url = os.getenv("BOT_DATABASE_URL", "")
if not db_url:
    print("ERROR: BOT_DATABASE_URL not set. Set it before running.")
    sys.exit(1)

from sqlalchemy import create_engine, text

engine = create_engine(db_url)

migrations = [
    "ALTER TABLE bot_quotas ADD COLUMN IF NOT EXISTS study_type VARCHAR DEFAULT 'STANDARD'",
    "ALTER TABLE bot_quotas ADD COLUMN IF NOT EXISTS store_id INTEGER",
    "ALTER TABLE bot_quotas ADD COLUMN IF NOT EXISTS planned_supervisor VARCHAR",
    "ALTER TABLE bot_quotas ADD COLUMN IF NOT EXISTS planned_interviewer VARCHAR",
]

with engine.connect() as conn:
    for sql in migrations:
        try:
            conn.execute(text(sql))
            conn.commit()
            print(f"✅ OK: {sql[:60]}...")
        except Exception as e:
            print(f"⚠️  Skipped (may already exist): {e}")

print("\nMigration complete.")
