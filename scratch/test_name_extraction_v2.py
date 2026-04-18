import os
import sys

# Change to root to avoid relative import issues
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.getcwd())

from backend import main, models
from unittest.mock import MagicMock

# Define aliases for test
main.POINT_TYPE_ALIASES = {
    "Centro Comercial": ["cc"],
    "Parque": ["pq"],
}

# Mock Quotas
q1 = models.BotQuota(id=1, category="General", value="Hombre | 14-17", target_count=10, current_count=0, study_code="S1")
q2 = models.BotQuota(id=2, category="Tipo de Punto", value="Parque", target_count=10, current_count=0, study_code="S1")
all_quotas = [q1, q2]

def test_logic(msg):
    db_mock = MagicMock()
    db_mock.query().filter().all.return_value = all_quotas
    
    results, name, err = main.check_free_text_quota(db_mock, "S1", msg)
    
    print(f"\nMSG: '{msg}'")
    if err:
        print(f"ERROR: {err}")
    else:
        q_labels = [f"{q.category} | {q.value}" for q in results]
        print(f"QUOTAS: {q_labels}")
        print(f"NAME: '{name}'")

# Run tests
test_logic("mb hombre 14-17 felipe")
test_logic("hombre 14-17 parque jorge monsalve")
test_logic("mb hombre 14-17")
test_logic("parque")
test_logic("hombre 14-17")
