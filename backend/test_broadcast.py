from sqlalchemy.orm import Session
import sys
import os
from datetime import datetime, date

# Add backend to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from backend import models, database, main

def simulate_broadcast():
    db = next(database.get_db())
    try:
        study = db.query(models.BotQuota.study_code).first()
        if not study:
            print("No studies found.")
            return
        
        study_code = study.study_code
        print(f"Testing broadcast for study: {study_code}")
        
        # 1. Check active phones
        active_phones = main.get_daily_active_phones_for_study(db, study_code)
        print(f"Active phones today: {active_phones}")
        
        # 2. Add current phone if not there
        test_phone = "573172376156"
        if test_phone not in active_phones:
            active_phones.append(test_phone)
        
        # 3. Simulate sending
        print(f"Simulating broadcast to: {active_phones}")
        # Note: This will actually call the real Meta API if the token is valid.
        # We'll just trace the call.
        main.send_quota_report_to_agents(db, study_code, active_phones, "[TEST BROADCAST] Nueva encuesta guardada.")
        
    finally:
        db.close()

if __name__ == "__main__":
    simulate_broadcast()
