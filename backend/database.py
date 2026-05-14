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

# 1. PATH RESOLUTION
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Shared DB in the 'az' sibling folder
SHARED_DB_PATH = os.path.abspath(os.path.join(BASE_DIR, '..', '..', 'az', 'az_marketing.db'))
# Local fallback if sibling is missing
LOCAL_BACKUP_DB = os.path.abspath(os.path.join(BASE_DIR, '..', 'bot_data.db'))

FINAL_SQLITE_PATH = SHARED_DB_PATH if os.path.exists(SHARED_DB_PATH) else LOCAL_BACKUP_DB
SQLITE_URL = f"sqlite:///{FINAL_SQLITE_PATH}"

# 2. ENGINES CONFIGURATION
BOT_DB_URL = os.getenv("BOT_DATABASE_URL")
USERS_DB_URL = os.getenv("USERS_DATABASE_URL") or os.getenv("DATABASE_URL")

def create_robust_engine(url, is_bot=True):
    if not url:
        print(f"INFO: No URL for {'Bot' if is_bot else 'Users'}. Using SQLite: {FINAL_SQLITE_PATH}")
        return create_engine(SQLITE_URL, connect_args={"check_same_thread": False})
    
    # Preparation
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    elif url.startswith("mysql://"):
        url = url.replace("mysql://", "mysql+pymysql://", 1)
    
    engine_kwargs = {
        "pool_pre_ping": True,
        "pool_recycle": 280
    }
    
    if "sqlite" in url:
        return create_engine(url, connect_args={"check_same_thread": False})
    else:
        # Add timeout to avoid hanging
        engine_kwargs["connect_args"] = {"connect_timeout": 10}
        
    try:
        engine = create_engine(url, **engine_kwargs)
        # Test connection
        with engine.connect() as conn:
            pass
        return engine
    except Exception as e:
        print(f"ERROR: Falló conexión a {'Bot' if is_bot else 'Users'} DB externa ({e}). USANDO SQLITE.")
        return create_engine(SQLITE_URL, connect_args={"check_same_thread": False})

# Engines
bot_engine = create_robust_engine(BOT_DB_URL, is_bot=True)
users_engine = create_robust_engine(USERS_DB_URL, is_bot=False)

# Sessions
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=bot_engine)
UsersSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=users_engine)

Base = declarative_base()
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
