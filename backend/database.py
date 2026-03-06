from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os

# Connect to the existing az_marketing.db in the az folder for local dev
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_AZ_DB_PATH = os.path.abspath(os.path.join(BASE_DIR, '..', '..', 'az', 'az_marketing.db'))

# 1. BOT DATABASE (Read/Write for Quotas and Sessions)
# Defaults to a local sqlite file in the backend folder
BOT_DB_URL = os.getenv("BOT_DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'bot_data.db')}")

# Fix for Render: SQLAlchemy expects postgresql:// but Render provides postgres://
if BOT_DB_URL.startswith("postgres://"):
    BOT_DB_URL = BOT_DB_URL.replace("postgres://", "postgresql://", 1)
if BOT_DB_URL.startswith("mysql://"):
    BOT_DB_URL = BOT_DB_URL.replace("mysql://", "mysql+pymysql://", 1)

bot_engine = create_engine(
    BOT_DB_URL, 
    connect_args={"check_same_thread": False} if "sqlite" in BOT_DB_URL else {},
    pool_recycle=280 if "mysql" in BOT_DB_URL else -1 # Prevent "Gone away" for MySQL
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=bot_engine)
Base = declarative_base()

# 2. USERS DATABASE (Strictly Read-Only from Click Panda SQL or local testing AZ)
USERS_DB_URL = os.getenv("USERS_DATABASE_URL", f"sqlite:///{LOCAL_AZ_DB_PATH}")

if USERS_DB_URL.startswith("postgres://"):
    USERS_DB_URL = USERS_DB_URL.replace("postgres://", "postgresql://", 1)
if USERS_DB_URL.startswith("mysql://"):
    USERS_DB_URL = USERS_DB_URL.replace("mysql://", "mysql+pymysql://", 1)

users_engine = create_engine(
    USERS_DB_URL, 
    connect_args={"check_same_thread": False} if "sqlite" in USERS_DB_URL else {},
    pool_recycle=280 if "mysql" in USERS_DB_URL else -1
)
UsersSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=users_engine)
UsersBase = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_users_db():
    db = UsersSessionLocal()
    try:
        yield db
    finally:
        db.close()
