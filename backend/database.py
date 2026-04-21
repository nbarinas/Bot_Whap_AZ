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

if BOT_DB_URL.startswith("postgres://"):
    BOT_DB_URL = BOT_DB_URL.replace("postgres://", "postgresql://", 1)
if BOT_DB_URL.startswith("mysql://"):
    BOT_DB_URL = BOT_DB_URL.replace("mysql://", "mysql+pymysql://", 1)

shared_engine_args = {
    "pool_size": 10,
    "max_overflow": 20,
    "pool_pre_ping": True,
}

def get_engine_args(url):
    args = shared_engine_args.copy()
    if "mysql" in url:
        args["pool_recycle"] = 280
        args["connect_args"] = {"connect_timeout": 10}
    elif "postgresql" in url:
        args["connect_args"] = {"connect_timeout": 10}
    elif "sqlite" in url:
        args["connect_args"] = {"check_same_thread": False}
    return args

bot_engine = create_engine(BOT_DB_URL, **get_engine_args(BOT_DB_URL))
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=bot_engine)
Base = declarative_base()

# Bot Fallback Engine
bot_fallback_engine = create_engine(f"sqlite:///{os.path.join(BASE_DIR, 'bot_data.db')}", connect_args={"check_same_thread": False})
BotFallbackSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=bot_fallback_engine)

# 2. USERS DATABASE (Strictly Read-Only from Click Panda SQL or local testing AZ)
USERS_DB_URL = os.getenv("USERS_DATABASE_URL") or os.getenv("DATABASE_URL") or f"sqlite:///{LOCAL_AZ_DB_PATH}"

if USERS_DB_URL.startswith("postgres://"):
    USERS_DB_URL = USERS_DB_URL.replace("postgres://", "postgresql://", 1)
if USERS_DB_URL.startswith("mysql://"):
    USERS_DB_URL = USERS_DB_URL.replace("mysql://", "mysql+pymysql://", 1)

users_engine = create_engine(USERS_DB_URL, **get_engine_args(USERS_DB_URL))
UsersSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=users_engine)
UsersBase = declarative_base()

# Users Fallback Engine
users_fallback_engine = create_engine(f"sqlite:///{LOCAL_AZ_DB_PATH}", connect_args={"check_same_thread": False})
UsersFallbackSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=users_fallback_engine)

def get_db():
    """
    Tries to connect to the primary Bot DB.
    Falls back to local SQLite if it fails.
    """
    db_type = "Primary"
    try:
        # Quick test for non-sqlite
        if "sqlite" not in BOT_DB_URL:
            with bot_engine.connect() as conn:
                pass
        db = SessionLocal()
    except Exception as e:
        print(f"WARNING: Bot Primary DB Unreachable ({e}). Initializing fallback.")
        db = BotFallbackSessionLocal()
        db_type = "Fallback"
    
    try:
        yield db
    finally:
        db.close()

def get_users_db():
    """
    Tries to connect to the primary Users DB (from Environment).
    Falls back to local SQLite if it fails.
    """
    db_type = "Primary"
    try:
        # Quick test for non-sqlite
        if "sqlite" not in USERS_DB_URL:
            with users_engine.connect() as conn:
                pass
        db = UsersSessionLocal()
    except Exception as e:
        print(f"WARNING: Users Primary DB Unreachable ({e}). Initializing fallback.")
        db = UsersFallbackSessionLocal()
        db_type = "Fallback"
    
    try:
        yield db
    finally:
        db.close()
