from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Boolean
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
    # La tabla `users` ya traia estas columnas; el modelo no las declaraba y
    # por eso el buscador de nombres y los reportes salian vacios.
    full_name = Column(String(255), nullable=True)
    city = Column(String(100), nullable=True)
    address = Column(String(255), nullable=True)
    photo_base64 = Column(Text, nullable=True)

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

class BotClosingRow(Base):
    """Cierre diario de campo: una fila por persona + dia + estudio.

    No se guardan nombres: solo los `users.id`. El formulario siempre elige
    del roster existente (`buscar_personas`), asi que el id siempre esta.
    Los nombres se resuelven al leer con `_nombre_de_usuario`.
    """
    __tablename__ = "bot_closing_rows"
    
    id = Column(Integer, primary_key=True, index=True)
    close_date = Column(String(10), index=True)          # YYYY-MM-DD (hora Colombia)
    study_code = Column(String(50), index=True)
    
    supervisor_id = Column(Integer, index=True, nullable=True)    # users.id
    interviewer_id = Column(Integer, index=True, nullable=True)   # users.id
    
    # Lo que declara el supervisor (censos) contra lo que tiene el sistema (encuestas)
    surveys_declared = Column(Integer, default=0)   # VINCULANTE: debe sumar el total real
    census_declared = Column(Integer, default=0)    # informativo, no se valida
    system_surveys = Column(Integer, default=0)     # foto del sistema al momento de guardar
    system_census = Column(Integer, default=0)
    
    # Dinero del dia (se pregunta una vez por persona, no por estudio)
    incentive_agent = Column(Integer, default=0)           # 0 = no, 1 = si
    incentive_agent_amount = Column(Integer, nullable=True)
    incentive_supervisor = Column(Integer, default=0)      # 0 = no, 1 = si
    incentive_supervisor_amount = Column(Integer, nullable=True)
    transport_full = Column(Integer, default=0)            # transportes completos pagados
    transport_partial = Column(Integer, default=0)         # transportes medios
    extra_expense_desc = Column(String(150), nullable=True)
    extra_expense_amount = Column(Integer, nullable=True)
    
    # 1 en la primera fila del dia de la persona, para que el TOTAL no duplique la plata
    is_charging_owner = Column(Integer, default=1)
    
    note = Column(Text, nullable=True)
    filled_by = Column(String(50), nullable=True)         # telefono del supervisor que lleno
    filled_at = Column(DateTime(timezone=True), server_default=func.now())
