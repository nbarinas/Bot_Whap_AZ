from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Boolean, UniqueConstraint
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

class BotStudy(Base):
    __tablename__ = "bot_studies"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), unique=True, index=True)
    study_type = Column(String(20), default='STANDARD') # 'STANDARD' or 'TDC'
    is_closed = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    quotas = relationship("BotQuota", back_populates="study")
    updates = relationship("BotQuotaUpdate", back_populates="study")
    subscriptions = relationship("BotStudySubscription", back_populates="study")

class BotQuota(Base):
    __tablename__ = "bot_quotas"
    
    id = Column(Integer, primary_key=True, index=True)
    study_id = Column(Integer, ForeignKey("bot_studies.id"), nullable=True)
    study_code = Column(String(50), index=True) 
    category = Column(String(50)) 
    value = Column(String(100)) 
    target_count = Column(Integer, default=0) 
    current_count = Column(Integer, default=0) 
    is_closed = Column(Integer, default=0) # 0 = open, 1 = closed
    point_type = Column(String(100), nullable=True)
    study_type = Column(String(20), default='STANDARD')  # 'STANDARD' or 'TDC'
    store_id = Column(Integer, nullable=True)              # TDC: número de tienda
    planned_supervisor = Column(String(100), nullable=True)
    planned_interviewer = Column(String(100), nullable=True)
    
    study = relationship("BotStudy", back_populates="quotas")
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class BotActiveAgent(Base):
    __tablename__ = "bot_active_agents"
    phone_number = Column(String(50), primary_key=True)
    assigned_studies = Column(String(500), nullable=True)


class BotAgentInterviewer(Base):
    """Encuestadores (personal) que un agente puede reportar en un estudio permitido.

    El vinculo es por par (telefono del agente, estudio): cada estudio permitido
    tiene su propia lista, independiente del resto.
    """
    __tablename__ = "bot_agent_interviewers"

    id = Column(Integer, primary_key=True, index=True)
    agent_phone = Column(String(50), index=True, nullable=False)
    study_code = Column(String(50), index=True, nullable=False)
    interviewer_name = Column(String(120), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "agent_phone", "study_code", "interviewer_name",
            name="uq_bot_agent_interviewer",
        ),
    )

class BotDailyClosing(Base):
    """Cierre del dia: uno por supervisor, fecha y estudio."""
    __tablename__ = "bot_daily_closings"

    id = Column(Integer, primary_key=True, index=True)
    close_date = Column(String(10), index=True, nullable=False)   # YYYY-MM-DD hora Colombia
    study_code = Column(String(50), index=True, nullable=False)
    supervisor_phone = Column(String(50), index=True, nullable=False)
    supervisor_name = Column(String(120), nullable=True)
    filled_by = Column(String(50), nullable=True)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint(
            "close_date", "study_code", "supervisor_phone",
            name="uq_bot_daily_closing",
        ),
    )


class BotDailyClosingLine(Base):
    """Lo declarado por persona en un cierre: censos por tipo, transporte e incentivo."""
    __tablename__ = "bot_daily_closing_lines"

    id = Column(Integer, primary_key=True, index=True)
    closing_id = Column(Integer, ForeignKey("bot_daily_closings.id"), index=True, nullable=False)
    interviewer_name = Column(String(120), nullable=False)
    surveys_system = Column(Integer, default=0)    # foto del sistema al cerrar
    census_generic = Column(Integer, default=0)
    census_23 = Column(Integer, default=0)
    census_4 = Column(Integer, default=0)
    transport_amount = Column(Integer, default=0)
    incentive_amount = Column(Integer, default=0)


class BotReferral(Base):
    __tablename__ = "bot_referrals"
    
    id = Column(Integer, primary_key=True, index=True)
    referral_phone = Column(String(50), index=True)
    referrer_phone = Column(String(50))
    full_name = Column(String(100))
    gender = Column(String(50))
    age = Column(Integer)
    city = Column(String(100))
    neighborhood = Column(String(150))
    address = Column(String(200))
    consent = Column(Boolean, default=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class BotQuotaUpdate(Base):
    __tablename__ = "bot_quota_updates"
    
    id = Column(Integer, primary_key=True, index=True)
    study_id = Column(Integer, ForeignKey("bot_studies.id"), nullable=True)
    study_code = Column(String(50), index=True)
    phone_number = Column(String(50)) # WhatsApp number instead of generic user_id
    message_text = Column(String(500)) 
    parsed_updates = Column(Text) 
    
    study = relationship("BotStudy", back_populates="updates")
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class QuotaSubmission(Base):
    __tablename__ = "quota_submissions"
    
    id = Column(Integer, primary_key=True, index=True)
    bot_quota_id = Column(Integer, ForeignKey("bot_quotas.id"), index=True)
    phone_number = Column(String(50), index=True) 
    submitted_at = Column(DateTime(timezone=True), server_default=func.now())
    is_deleted = Column(Integer, default=0) # Soft delete (0=active, 1=deleted)
    interviewer_name = Column(String(100), nullable=True)
    supervisor_name = Column(String(100), nullable=True)
    visit_date = Column(String(20), nullable=True)  # TDC: fecha del día de visita

class BotSession(Base):
    __tablename__ = "bot_sessions"
    
    phone_number = Column(String(50), primary_key=True)
    state = Column(String(50), default="IDLE")
    context_data = Column(Text, default="{}") # JSON containing study_code, action, and selected_path
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

class BotStudySubscription(Base):
    __tablename__ = "bot_study_subscriptions"
    
    id = Column(Integer, primary_key=True, index=True)
    study_id = Column(Integer, ForeignKey("bot_studies.id"), nullable=True)
    phone_number = Column(String(50), index=True)
    study_code = Column(String(50), index=True)
    subscribed_at = Column(DateTime(timezone=True), server_default=func.now())
    
    study = relationship("BotStudy", back_populates="subscriptions")
