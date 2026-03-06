import os
import sys

# Add backend directory to path so we can import models and database
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from backend.database import engine, Base
from backend.models import BotQuota, BotQuotaUpdate

def upgrade():
    print("Creating Bot Quota tables...")
    BotQuota.__table__.create(engine, checkfirst=True)
    BotQuotaUpdate.__table__.create(engine, checkfirst=True)
    print("Migration completed successfully.")

if __name__ == "__main__":
    upgrade()
