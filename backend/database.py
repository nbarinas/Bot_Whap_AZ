from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os

# Connect to the existing az_marketing.db in the az folder for local dev
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Note: assuming 'backend' and 'az' are siblings in the root folder
# Check for sibling 'az' folder to share DB locally, fallback to root DB
SIBLING_AZ_DB = os.path.abspath(os.path.join(BASE_DIR, '..', '..', 'az', 'az_marketing.db'))
ROOT_AZ_DB = os.path.abspath(os.path.join(BASE_DIR, '..', 'az_marketing.db'))

LOCAL_AZ_DB_PATH = SIBLING_AZ_DB if os.path.exists(SIBLING_AZ_DB) else ROOT_AZ_DB

# 1. BOT DATABASE (Read/Write for Quotas and Sessions)
# Defaults to a local sqlite file in the backend folder
BOT_DB_URL = os.getenv("BOT_DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'bot_data.db')}")

# Fix for Render: SQLAlchemy expects postgresql:// but Render provides postgres://
if BOT_DB_URL.startswith("postgres://"):
    BOT_DB_URL = BOT_DB_URL.replace("postgres://", "postgresql://", 1)
if BOT_DB_URL.startswith("mysql://"):
    BOT_DB_URL = BOT_DB_URL.replace("mysql://", "mysql+pymysql://", 1)

bot_engine_args = {
    "pool_size": 10,
    "max_overflow": 20,
    "pool_pre_ping": True,
}

# Add timeouts for MySQL/Postgres to avoid hanging
if "mysql" in BOT_DB_URL:
    bot_engine_args["pool_recycle"] = 280
    bot_engine_args["connect_args"] = {"connect_timeout": 10}
elif "postgresql" in BOT_DB_URL:
    bot_engine_args["connect_args"] = {"connect_timeout": 10}
elif "sqlite" in BOT_DB_URL:
    bot_engine_args["connect_args"] = {"check_same_thread": False}

bot_engine = create_engine(BOT_DB_URL, **bot_engine_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=bot_engine)
Base = declarative_base()

# 2. USERS DATABASE (Strictly Read-Only from Click Panda SQL or local testing AZ)
USERS_DB_URL = os.getenv("USERS_DATABASE_URL") or os.getenv("DATABASE_URL") or f"sqlite:///{LOCAL_AZ_DB_PATH}"

if USERS_DB_URL.startswith("postgres://"):
    USERS_DB_URL = USERS_DB_URL.replace("postgres://", "postgresql://", 1)
if USERS_DB_URL.startswith("mysql://"):
    USERS_DB_URL = USERS_DB_URL.replace("mysql://", "mysql+pymysql://", 1)

users_engine_args = {
    "pool_size": 10,
    "max_overflow": 20,
    "pool_pre_ping": True,
}

if "mysql" in USERS_DB_URL:
    users_engine_args["pool_recycle"] = 280
    users_engine_args["connect_args"] = {"connect_timeout": 10}
elif "postgresql" in USERS_DB_URL:
    users_engine_args["connect_args"] = {"connect_timeout": 10}
elif "sqlite" in USERS_DB_URL:
    users_engine_args["connect_args"] = {"check_same_thread": False}

users_engine = create_engine(USERS_DB_URL, **users_engine_args)
UsersSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=users_engine)
UsersBase = declarative_base()

# Supplemental Engine for Failover (Always SQLite)
fallback_engine = create_engine(f"sqlite:///{LOCAL_AZ_DB_PATH}", connect_args={"check_same_thread": False})
FallbackSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=fallback_engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_users_db():
    """
    Tries to connect to the primary Users DB (MySQL/Postgres).
    If it fails after 10s timeout, it falls back to the local SQLite file.
    """
    try:
        # Test connection quickly
        with users_engine.connect() as conn:
            pass
        db = UsersSessionLocal()
        print(f"DEBUG: Using Primary DB ({USERS_DB_URL.split('@')[-1] if '@' in USERS_DB_URL else USERS_DB_URL})")
    except Exception as e:
        print(f"WARNING: Primary DB Unreachable ({e}). Falling back to local SQLite.")
        db = FallbackSessionLocal()
    
    try:
        yield db
    finally:
        db.close()
