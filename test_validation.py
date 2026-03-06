import sys
import os
import time
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.database import engine, SessionLocal
from backend.main import process_bot_message
from backend import models
from datetime import datetime, timedelta, timezone

db = SessionLocal()

print("--- Test 3: Timeout ---")
# First create a state
process_bot_message("0000", "hola", db)
session = db.query(models.BotSession).filter(models.BotSession.phone_number == "0000").first()
session.state = "WAITING_STUDY"
db.commit()

# Set updated_at to 6 minutes ago
from sqlalchemy import text
db.execute(text("UPDATE bot_sessions SET updated_at = datetime('now', '-6 minutes') WHERE phone_number = '0000'"))
db.commit()

reply = process_bot_message("0000", "1", db)
print(reply)
