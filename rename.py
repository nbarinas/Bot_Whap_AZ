import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.database import engine
from sqlalchemy import text

with engine.connect() as conn:
    conn.execute(text("ALTER TABLE bot_quota_updates RENAME COLUMN user_id TO phone_number;"))
    conn.commit()
    print("Renamed OK")
