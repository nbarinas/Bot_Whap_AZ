import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.database import engine, Base
from backend import models

print("Creating new tables...")
Base.metadata.create_all(bind=engine)
print("Done!")
