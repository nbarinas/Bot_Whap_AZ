import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.database import engine, SessionLocal
from backend import models

db = SessionLocal()
quotas = db.query(models.BotQuota).all()
for q in quotas:
    print(f"Study: {q.study_code}, Cat: '{q.category}', Val: '{q.value}'")
