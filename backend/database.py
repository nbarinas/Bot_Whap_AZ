from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os

# Connect to the existing az_marketing.db in the az folder
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# ../../az/az_marketing.db
DB_PATH = os.path.abspath(os.path.join(BASE_DIR, '..', '..', 'az', 'az_marketing.db'))

SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
