from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base, UsersBase

class User(UsersBase):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True)
    hashed_password = Column(String(200))
    role = Column(String(50))
    phone_number = Column(String(20))
    last_seen = Column(DateTime)

class BotQuota(Base):
    __tablename__ = "bot_quotas"
    
    id = Column(Integer, primary_key=True, index=True)
    study_code = Column(String(50), index=True) 
    category = Column(String(50)) 
    value = Column(String(100)) 
    target_count = Column(Integer, default=0) 
    current_count = Column(Integer, default=0) 
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class BotQuotaUpdate(Base):
    __tablename__ = "bot_quota_updates"
    
    id = Column(Integer, primary_key=True, index=True)
    study_code = Column(String(50), index=True)
    phone_number = Column(String(50)) # WhatsApp number instead of generic user_id
    message_text = Column(String(500)) 
    parsed_updates = Column(Text) 
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class QuotaSubmission(Base):
    __tablename__ = "quota_submissions"
    
    id = Column(Integer, primary_key=True, index=True)
    bot_quota_id = Column(Integer, ForeignKey("bot_quotas.id"), index=True)
    phone_number = Column(String(50), index=True) 
    submitted_at = Column(DateTime(timezone=True), server_default=func.now())
    is_deleted = Column(Integer, default=0) # Soft delete (0=active, 1=deleted)

class BotSession(Base):
    __tablename__ = "bot_sessions"
    
    phone_number = Column(String(50), primary_key=True)
    state = Column(String(50), default="IDLE")
    context_data = Column(Text, default="{}") # JSON containing study_code, action, and selected_path
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
