import os
import sys
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Setup path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend import models

# Mock DB
engine = create_engine('sqlite:///:memory:')
models.Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
db = Session()

# Setup test data
study_code = "TEST01"
# Demographic quotas
db.add(models.BotQuota(study_code=study_code, category="Hombre", value="18-25", target_count=10, current_count=0))
db.add(models.BotQuota(study_code=study_code, category="Mujer", value="18-25", target_count=10, current_count=0))
# Point Type quotas
db.add(models.BotQuota(study_code=study_code, category="Tipo de Punto", value="Parque", target_count=10, current_count=0))
db.add(models.BotQuota(study_code=study_code, category="Tipo de Punto", value="Iglesia", target_count=10, current_count=0))
db.commit()

# Import the function from main.py
# (We might need to mock some things if main.py does a lot on import)
from backend.main import check_free_text_quota

def test_validation():
    print("Testing check_free_text_quota...")
    
    # 1. Full match
    res, msg = check_free_text_quota(db, study_code, "hombre 18-25 parque")
    print(f"Full Match Result: {[r.category + ' | ' + r.value for r in res]}")
    assert len(res) == 2, "Should match 2 quotas"
    
    # 2. Demographic only (This should fail after our fix)
    res, msg = check_free_text_quota(db, study_code, "hombre 18-25")
    print(f"Demo Only Result: {[r.category + ' | ' + r.value for r in res]}")
    # Currently this passes and returns length 1.
    
    # 3. Point only (This should fail after our fix)
    res, msg = check_free_text_quota(db, study_code, "parque")
    print(f"Point Only Result: {[r.category + ' | ' + r.value for r in res]}")
    # Currently this passes and returns length 1.

if __name__ == "__main__":
    try:
        test_validation()
    except Exception as e:
        print(f"Test Failed: {e}")
