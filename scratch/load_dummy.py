import sys
import os
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import random

# Add current directory to path
sys.path.append(os.getcwd())

from backend import models, database

def load_dummy_data(study_code="jsdflkjd"):
    # We use the local SQLite by default if BOT_DB_URL is sqlite
    # But let's just use the engine configured in database.py
    engine = database.bot_engine
    SessionLocal = database.SessionLocal
    
    db = SessionLocal()
    try:
        # 1. Find the quotas for this study
        quotas = db.query(models.BotQuota).filter(models.BotQuota.study_code == study_code).all()
        if not quotas:
            print(f"No se encontraron cuotas para el estudio {study_code}")
            return
        
        print(f"Cargando datos dummy para el estudio {study_code} ({len(quotas)} cuotas encontradas)...")
        
        supervisors = ["3136623816", "3001846907", "3112223344"]
        interviewers = ["Carlos Ruiz", "Marta Lopez", "Diego Torres", "Elena Gomez"]
        
        total_created = 0
        
        # Create about 20-30 random submissions
        for _ in range(25):
            quota = random.choice(quotas)
            
            # Create submission
            sub = models.QuotaSubmission(
                bot_quota_id=quota.id,
                phone_number=random.choice(supervisors),
                interviewer_name=random.choice(interviewers),
                submitted_at=datetime.now() - timedelta(hours=random.randint(0, 48))
            )
            db.add(sub)
            
            # Update current count
            quota.current_count += 1
            total_created += 1
            
        db.commit()
        print(f"¡Éxito! Se crearon {total_created} registros dummy.")
        
    except Exception as e:
        db.rollback()
        print(f"Error cargando datos: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    # Check if a study code was provided as argument
    code = "jsdflkjd"
    if len(sys.argv) > 1:
        code = sys.argv[1]
    load_dummy_data(code)
