from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
import os
from fastapi.security import OAuth2PasswordRequestForm

from . import models, database, auth

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(os.path.dirname(BASE_DIR), "frontend")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from fastapi.staticfiles import StaticFiles
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

@app.on_event("startup")
def on_startup():
    models.Base.metadata.create_all(bind=database.bot_engine)
    try:
        from sqlalchemy import text
        with database.bot_engine.begin() as conn:
            conn.execute(text("ALTER TABLE bot_quotas ADD COLUMN is_closed INTEGER DEFAULT 0"))
    except Exception:
        pass # Column presumably exists

@app.get("/")
def read_root():
    return FileResponse(os.path.join(FRONTEND_DIR, "quotas.html"))

@app.get("/login")
def login_page():
    return FileResponse(os.path.join(FRONTEND_DIR, "login.html"))

@app.post("/api/token")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db_users: Session = Depends(database.get_users_db)):
    user = db_users.query(models.User).filter(models.User.username == form_data.username).first()
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # Ensure role is superuser or coordinator
    if user.role not in ["superuser", "coordinator"]:
        raise HTTPException(
            status_code=403,
            detail="Not authorized to manage quotas",
        )
    access_token = auth.create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer", "role": user.role}

class QuotaCreateUpdate(BaseModel):
    study_code: str
    category: str
    value: str
    target_count: int

@app.get("/api/quotas")
def get_bot_quotas(study_code: Optional[str] = None, db: Session = Depends(database.get_db), current_user: models.User = Depends(auth.get_current_user)):
    query = db.query(models.BotQuota)
    if study_code:
        query = query.filter(models.BotQuota.study_code == study_code)
    quotas = query.all()
    
    result = {}
    for q in quotas:
        if q.study_code not in result:
            result[q.study_code] = []
        result[q.study_code].append({
            "id": q.id,
            "category": q.category,
            "value": q.value,
            "target_count": q.target_count,
            "current_count": q.current_count,
            "is_closed": q.is_closed
        })
    return result

@app.post("/api/quotas")
def create_or_update_quota(quota_in: QuotaCreateUpdate, db: Session = Depends(database.get_db), current_user: models.User = Depends(auth.get_current_user)):
    quota = db.query(models.BotQuota).filter(
        models.BotQuota.study_code == quota_in.study_code,
        models.BotQuota.category == quota_in.category,
        models.BotQuota.value == quota_in.value
    ).first()
    
    if quota:
        quota.target_count = quota_in.target_count
        db.commit()
        db.refresh(quota)
        return {"msg": "Quota updated", "id": quota.id}
    else:
        new_quota = models.BotQuota(
            study_code=quota_in.study_code,
            category=quota_in.category,
            value=quota_in.value,
            target_count=quota_in.target_count,
            current_count=0
        )
        db.add(new_quota)
        db.commit()
        db.refresh(new_quota)
        return {"msg": "Quota created", "id": new_quota.id}

@app.post("/api/quotas/batch")
def create_or_update_quotas_batch(quotas_in: list[QuotaCreateUpdate], db: Session = Depends(database.get_db), current_user: models.User = Depends(auth.get_current_user)):
    results = []
    for quota_in in quotas_in:
        quota = db.query(models.BotQuota).filter(
            models.BotQuota.study_code == quota_in.study_code,
            models.BotQuota.category == quota_in.category,
            models.BotQuota.value == quota_in.value
        ).first()
        
        if quota:
            quota.target_count = quota_in.target_count
            db.commit()
            db.refresh(quota)
            results.append(quota.id)
        else:
            new_quota = models.BotQuota(
                study_code=quota_in.study_code,
                category=quota_in.category,
                value=quota_in.value,
                target_count=quota_in.target_count,
                current_count=0
            )
            db.add(new_quota)
            db.commit()
            db.refresh(new_quota)
            results.append(new_quota.id)
    return {"msg": "Batch quotes processed", "ids": results}

@app.delete("/api/quotas/{quota_id}")
def delete_quota(quota_id: int, db: Session = Depends(database.get_db), current_user: models.User = Depends(auth.get_current_user)):
    quota = db.query(models.BotQuota).filter(models.BotQuota.id == quota_id).first()
    if not quota:
        raise HTTPException(status_code=404, detail="Quota not found")
        
    db.delete(quota)
    db.commit()
    return {"msg": "Quota deleted"}

@app.delete("/api/quotas/study/{study_code}")
def delete_study(study_code: str, db: Session = Depends(database.get_db), current_user: models.User = Depends(auth.get_current_user)):
    quotas = db.query(models.BotQuota).filter(models.BotQuota.study_code == study_code).all()
    if not quotas:
        raise HTTPException(status_code=404, detail="Study not found")
        
    for q in quotas:
        db.delete(q)
    db.commit()
    return {"msg": "Study deleted"}

@app.put("/api/quotas/study/{study_code}/toggle-status")
def toggle_study_status(study_code: str, db: Session = Depends(database.get_db), current_user: models.User = Depends(auth.get_current_user)):
    quotas = db.query(models.BotQuota).filter(models.BotQuota.study_code == study_code).all()
    if not quotas:
        raise HTTPException(status_code=404, detail="Study not found")
        
    new_status = 1 if quotas[0].is_closed == 0 else 0
    for q in quotas:
        q.is_closed = new_status
    db.commit()
    return {"msg": f"Study {'closed' if new_status else 'opened'}", "is_closed": new_status}

@app.get("/api/agents")
def get_agents(db: Session = Depends(database.get_db), db_users: Session = Depends(database.get_users_db), current_user: models.User = Depends(auth.get_current_user)):
    try:
        sql = text("SELECT username, phone_number, role, full_name FROM users WHERE phone_number IS NOT NULL AND phone_number != ''")
        all_users = db_users.execute(sql).fetchall()
    except Exception:
        # Fallback si no existe la columna full_name
        sql = text("SELECT username, phone_number, role, username as full_name FROM users WHERE phone_number IS NOT NULL AND phone_number != ''")
        all_users = db_users.execute(sql).fetchall()
        
    active_records = db.query(models.BotActiveAgent).all()
    active_phones = {record.phone_number for record in active_records}
    
    agents = []
    for u in all_users:
        if u.phone_number:
            agents.append({
                "username": u.username,
                "full_name": u.full_name if u.full_name else u.username,
                "phone_number": u.phone_number,
                "role": u.role,
                "is_active": u.phone_number in active_phones
            })
    return agents

class AgentToggleRequest(BaseModel):
    phone_number: str
    is_active: bool

@app.post("/api/agents/toggle")
def toggle_agent(req: AgentToggleRequest, db: Session = Depends(database.get_db), current_user: models.User = Depends(auth.get_current_user)):
    record = db.query(models.BotActiveAgent).filter(models.BotActiveAgent.phone_number == req.phone_number).first()
    if req.is_active and not record:
        new_agent = models.BotActiveAgent(phone_number=req.phone_number)
        db.add(new_agent)
    elif not req.is_active and record:
        db.delete(record)
        
    db.commit()
    return {"msg": "Agent status updated"}

class WebhookSimulateRequest(BaseModel):
    phone_number: str
    message: str

import re
import json
import requests
from sqlalchemy import text

# WhatsApp Configuration Constants (Use environment variables in production)
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "EAAXs5LUMDHoBQ3gidC32OLGzDEZC4uhZCAWI0WNVvk8nnKg4ewiYo4a0pQi9qhjhXwAZC94UoSg6BsPQzFqjPIYiTu6rQqkhqihEbIG5zfKTpqN3tcrce9dUR4UOCYR7qKYov3IILAcUcQUJjuAIZBZBo5koizRGSI7vBUkmD8nV2aK8xqwLAfoCR3MWWvAG6sF5GfInh5sBdQz6nPsR9fowIYhkKK3f8r80r5GJHTlSohpiWwEZB7rowThW38oH3PANfXZANosc8sFhZBwYKAaCZAR719T0ZA9rUZD")
WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID", "969902462880750")
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATS_VERIFY_TOKEN", "azbot_secreto_2026")

def send_whatsapp_message(to_phone: str, message_text: str):
    url = f"https://graph.facebook.com/v22.0/{WHATSAPP_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    data = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "text",
        "text": {
            "body": message_text
        }
    }
    try:
        response = requests.post(url, headers=headers, data=json.dumps(data))
        if response.status_code != 200:
            print(f"META ERROR RESPONSE: {response.text}")
        response.raise_for_status()
        print(f"WhatsApp message successfully sent to {to_phone}")
    except Exception as e:
        print(f"Error sending WhatsApp message to {to_phone}: {str(e)}")

def send_whatsapp_media(to_phone: str, media_type: str, media_id: str, caption: str = None):
    """
    Sends an image or video using its Meta media_id.
    media_type: 'image' or 'video'
    """
    url = f"https://graph.facebook.com/v22.0/{WHATSAPP_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    
    data = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": media_type,
        media_type: {
            "id": media_id
        }
    }
    
    if caption and media_type == 'image':
        data["image"]["caption"] = caption
    elif caption and media_type == 'video':
        data["video"]["caption"] = caption

    try:
        response = requests.post(url, headers=headers, data=json.dumps(data))
        if response.status_code != 200:
            print(f"META ERROR RESPONSE (MEDIA): {response.text}")
        response.raise_for_status()
        print(f"WhatsApp {media_type} successfully sent to {to_phone}")
    except Exception as e:
        print(f"Error sending WhatsApp {media_type} to {to_phone}: {str(e)}")


from fastapi import Request

@app.get("/api/bot/webhook")
async def verify_whatsapp_webhook(request: Request):
    """
    Required for Meta webhook verification.
    When you configure the webhook in the Meta App Dashboard, Meta will send a GET request here.
    """
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode and token:
        if mode == "subscribe" and token == WHATSAPP_VERIFY_TOKEN:
            print("WEBHOOK_VERIFIED")
            return int(challenge)
        else:
            raise HTTPException(status_code=403, detail="Verification token mismatch")
    raise HTTPException(status_code=400, detail="Missing parameters")


@app.post("/api/bot/webhook")
async def receive_whatsapp_webhook(request: Request, db: Session = Depends(database.get_db), db_users: Session = Depends(database.get_users_db)):
    """
    Receives incoming WhatsApp messages from Meta natively.
    """
    body = await request.json()
    
    # Meta sends a specific JSON structure for WhatsApp messages
    if body.get("object") == "whatsapp_business_account":
        try:
            for entry in body.get("entry", []):
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    # Check if it has a message (not just a status update like 'delivered'/'read')
                    if "messages" in value:
                        for msg_data in value["messages"]:
                            # Meta includes the country code, e.g., "573172376156"
                            phone = msg_data.get("from")
                            # We only handle text messages right now
                            if msg_data.get("type") == "text":
                                text_msg = msg_data["text"]["body"]
                                print(f"Received WhatsApp MSG from {phone}: {text_msg}")
                                
                                # Process it using our core logic
                                process_bot_message(phone, text_msg, db, db_users)
                                
            return {"status": "ok"}
        except Exception as e:
            print(f"Error processing webhook: {e}")
            return {"status": "error"}
    else:
        # Not a WhatsApp event
        raise HTTPException(status_code=404)


@app.post("/api/bot/webhook-simulate")
def simulate_whatsapp_webhook(req: WebhookSimulateRequest, db: Session = Depends(database.get_db), db_users: Session = Depends(database.get_users_db)):
    """
    Legacy/Simulator endpoint used by the frontend.
    """
    reply = process_bot_message(req.phone_number, req.message, db, db_users)
    return {"reply": reply}


def process_bot_message(phone_raw: str, message_raw: str, db: Session, db_users: Session) -> str:
    """
    Core bot logic extracted from the simulator so both endpoints can share it.
    """
    msg = message_raw.strip().lower()
    phone = phone_raw.strip()
    
    # Check for numbers saved with or without the '57' prefix
    normalized_phone = phone
    if phone.startswith("57") and len(phone) == 12:
        normalized_phone = phone[2:]
    
    # 1. Authorize User for Quota Management
    sql = text("SELECT role, full_name FROM users WHERE phone_number = :p OR phone_number = :np")
    try:
        user_record = db_users.execute(sql, {"p": phone, "np": normalized_phone}).first()
    except Exception:
        # Fallback si no existe la columna full_name
        sql = text("SELECT role, username as full_name FROM users WHERE phone_number = :p OR phone_number = :np")
        user_record = db_users.execute(sql, {"p": phone, "np": normalized_phone}).first()
    
    is_in_base = bool(user_record)
    agent_name = ""
    if user_record and hasattr(user_record, 'full_name') and user_record.full_name:
        agent_name = user_record.full_name.split(" ")[0].capitalize() # Solo el primer nombre
    elif phone == "0000":
        agent_name = "Admin"
    
    active_agent = db.query(models.BotActiveAgent).filter(
        (models.BotActiveAgent.phone_number == phone) | 
        (models.BotActiveAgent.phone_number == normalized_phone)
    ).first()
    is_active = bool(active_agent)
    
    user_type = "UNKNOWN"
    if (is_active and is_in_base) or phone == "0000":
        user_type = "AGENT"
    elif is_in_base:
        user_type = "INACTIVE_AGENT"
    else:
        # Check if in calls
        calls_sql = text("SELECT id FROM calls WHERE phone_number = :p OR phone_number = :np")
        call_record = db_users.execute(calls_sql, {"p": phone, "np": normalized_phone}).first()
        if call_record:
            user_type = "RESPONDENT"
        else:
            user_type = "UNKNOWN"
            
    if user_type == "INACTIVE_AGENT":
        reply = "⚠️ Por el momento no estás activo para registrar cuotas."
        log = models.BotQuotaUpdate(
            study_code="UNAUTHORIZED",
            phone_number=phone,
            message_text=message_raw,
            parsed_updates=reply
        )
        db.add(log)
        db.commit()
        if phone != "0000":
            send_whatsapp_message(phone, reply)
        return reply
    
    from datetime import datetime, timedelta, timezone
    
    # Force restart keywords
    if msg in ["hola", "salir", "cancelar", "reiniciar", "menu"]:
        session = db.query(models.BotSession).filter(models.BotSession.phone_number == phone).first()
        if session:
            db.delete(session)
            db.commit()
    
    session = db.query(models.BotSession).filter(models.BotSession.phone_number == phone).first()
    
    timeout_message = ""
    if session and session.updated_at:
        now = datetime.now() # Use local server time
        session_time = session.updated_at.replace(tzinfo=None)
        
        # If difference is more than 5 minutes (300 seconds)
        if abs((now - session_time).total_seconds()) > 300:
            db.delete(session)
            db.commit()
            session = None
            timeout_message = "⌛ Tu sesión ha expirado por inactividad (5 min). Empecemos de nuevo.\n\n"

    if not session:
        session = models.BotSession(phone_number=phone, state="IDLE", context_data="{}")
        db.add(session)
        db.commit()
        db.refresh(session)
        
    ctx = json.loads(session.context_data)
    state = session.state
    reply = ""

    def handle_invalid(err_msg, options_text):
        attempts = ctx.get("invalid_attempts", 0) + 1
        if attempts >= 3:
            session.state = "IDLE"
            return "🚫 Demasiados intentos inválidos. La sesión se ha reiniciado.\n👋 Escribe 'Hola' para empezar de nuevo.", {}
        ctx["invalid_attempts"] = attempts
        return f"⚠️ {err_msg}\n\nOpciones disponibles:\n{options_text}", ctx

    if state == "IDLE":
        if user_type == "AGENT":
            # Ask for study
            studies = db.query(models.BotQuota.study_code).filter(models.BotQuota.is_closed == 0).distinct().all()
            if not studies:
                reply = timeout_message + "No hay estudios activos en este momento."
            else:
                study_list = [s[0] for s in studies]
                ctx["available_studies"] = study_list
                ctx["invalid_attempts"] = 0
                session.state = "WAITING_STUDY"
                
                opts = "\n".join([f"{i+1}. {s}" for i, s in enumerate(study_list)])
                greeting = f"¡Hola {agent_name}!" if agent_name else "¡Hola!"
                reply = timeout_message + f"{greeting} Selecciona el estudio en el que estás:\n{opts}"
                
        elif user_type == "RESPONDENT":
            calls_sql = text("SELECT study_id FROM calls WHERE phone_number = :p OR phone_number = :np")
            call_records = db_users.execute(calls_sql, {"p": phone, "np": normalized_phone}).fetchall()
            
            study_ids = [r.study_id for r in call_records if r.study_id]
            if not study_ids:
                user_type = "UNKNOWN"
            else:
                placeholders = ','.join([':p' + str(i) for i in range(len(study_ids))])
                params = {f"p{i}": sid for i, sid in enumerate(study_ids)}
                studies_sql = text(f"SELECT is_active, status, created_at FROM studies WHERE id IN ({placeholders})")
                studies_records = db_users.execute(studies_sql, params).fetchall()
                
                has_open = False
                has_closed = False
                closed_dates = []
                
                for sr in studies_records:
                    is_closed = (sr.is_active == 0) or (str(sr.status).lower() == 'cerrado')
                    if is_closed:
                        has_closed = True
                        if sr.created_at:
                            closed_dates.append(sr.created_at.strftime("%Y-%m-%d"))
                    else:
                        has_open = True
                        
                if has_open and not has_closed:
                    reply = timeout_message + "Tu participación ha sido registrada. Por el momento no se ha enviado la base de súperincentivos, en algunos días que cierre el estudio y luego de 15 días te llegará el proceso para que lo redimas. ¡Gracias por participar en nuestro estudio!"
                    db.delete(session)
                else:
                    date_str = closed_dates[0] if closed_dates else "recientemente"
                    reply = timeout_message + f"Tu participación fue en un estudio que cerró el {date_str}. Te debería llegar un mensaje de súperincentivos.\n\n¿Ya hiciste los pasos para redimir tu bono?\n1. Sí\n2. No"
                    session.state = "WAITING_BONUS_REDEEM_ANSWER"
                    ctx["invalid_attempts"] = 0

        if user_type == "UNKNOWN":
            reply = timeout_message + "¡Hola! Gracias por comunicarte con AZ Marketing. ¿En qué podemos ayudarte?\n1. Ver estado de un incentivo o bono\n2. Referir a un amig@ para estudios de mercadeo"
            session.state = "UNKNOWN_MENU"
            ctx["invalid_attempts"] = 0
            
    elif state == "WAITING_STUDY":
        available = ctx.get("available_studies", [])
        opts_text = "\n".join([f"{i+1}. {s}" for i, s in enumerate(available)])
        try:
            choice = int(msg) - 1
            if 0 <= choice < len(available):
                study_code = available[choice]
                ctx["study_code"] = study_code
                ctx["invalid_attempts"] = 0
                session.state = "WAITING_ACTION"
                reply = f"Estudio {study_code} seleccionado. ¿Qué deseas hacer?\n1. Añadir 1 encuesta\n2. Borrar mi última encuesta\n3. Ver cuotas actuales"
            else:
                reply, ctx = handle_invalid("Opción inválida. Responde con el número de la lista.", opts_text)
        except ValueError:
            reply, ctx = handle_invalid("Por favor, responde solo con el NÚMERO de la opción.", opts_text)

    elif state == "WAITING_ACTION":
        opts_text = "1. Añadir 1 encuesta\n2. Borrar mi última encuesta\n3. Ver cuotas actuales"
        if msg == "2":
            # Delete last submission
            study_code = ctx.get("study_code")
            study_quotas = db.query(models.BotQuota).filter(models.BotQuota.study_code == study_code).all()
            q_ids = [q.id for q in study_quotas]
            
            last_sub = db.query(models.QuotaSubmission).filter(
                models.QuotaSubmission.phone_number == phone,
                models.QuotaSubmission.bot_quota_id.in_(q_ids)
            ).order_by(models.QuotaSubmission.submitted_at.desc()).first()
            
            if last_sub:
                if last_sub.is_deleted == 1:
                    reply = "⚠️ Ya borraste tu última encuesta registrada. No puedes retroceder más."
                else:
                    last_sub.is_deleted = 1
                    quota = db.query(models.BotQuota).get(last_sub.bot_quota_id)
                    quota.current_count -= 1
                    
                    report = build_study_report(db, study_code)
                    reply = f"✅ Se ha borrado tu última encuesta registrada con éxito.\n{report}"
            else:
                reply = "⚠️ No tienes encuestas registradas recientes en este estudio para borrar."
                
            session.state = "IDLE"
            ctx = {}
            
        elif msg == "3":
            # View current matrix
            study_code = ctx.get("study_code")
            report = build_study_report(db, study_code)
            reply = report
            session.state = "IDLE"
            ctx = {}
            
        elif msg == "1":
            ctx["action"] = "ADD"
            ctx["selected_path"] = []
            ctx["invalid_attempts"] = 0
            reply, next_state = compute_next_bot_step(db, ctx, phone)
            session.state = next_state
        else:
            reply, ctx = handle_invalid("Responde 1 para Añadir, 2 para Borrar o 3 para Ver cuotas.", opts_text)

    elif state == "WAITING_CATEGORY":
        # Handle the category selection
        options = ctx.get("current_options", [])
        opts_text = "\n".join([f"{i+1}. {o}" for i, o in enumerate(options)])
        try:
            choice = int(msg) - 1
            if 0 <= choice < len(options):
                chosen_val = options[choice]
                ctx["selected_path"].append(chosen_val)
                ctx["invalid_attempts"] = 0
                # Compute next step
                reply, next_state = compute_next_bot_step(db, ctx, phone)
                session.state = next_state
                if next_state == "IDLE":
                    ctx = {} # Clean up
            else:
                reply, ctx = handle_invalid("Opción inválida. Responde con el número de la lista.", opts_text)
        except ValueError:
            reply, ctx = handle_invalid("Por favor, responde solo con el NÚMERO de la opción.", opts_text)

    # --- NUEVAS RUTAS: RESPONDENTS & DESCONOCIDOS ---
    
    elif state == "WAITING_BONUS_REDEEM_ANSWER":
        if msg == "1":
            reply = "¿Pudiste resolver para el bono exitosamente?\n1. Sí pude\n2. No pude"
            session.state = "WAITING_BONUS_RESOLVED"
        elif msg == "2":
            # IDs de los archivos en Meta (estos deben ser generados con un token válido)
            # Para bono.jpeg y Video Bono Comprimido.mp4
            IMAGE_ID = "1292705149412146" 
            VIDEO_ID = "934845532580264"
            
            if IMAGE_ID != "PENDIENTE_TOKEN_INVALIDO" and phone != "0000":
                send_whatsapp_media(phone, "image", IMAGE_ID, "📸 Imagen del bono")
                send_whatsapp_media(phone, "video", VIDEO_ID, "🎥 Video explicativo")

            reply = "Para redimir tu bono, por favor mira este video explicativo que te acabamos de enviar.\n\nDespués de ver el video o seguir los pasos, ¿pudiste resolver para tu bono?\n1. Sí pude\n2. No pude"
            session.state = "WAITING_BONUS_RESOLVED"
        else:
            reply = "⚠️ Opción inválida. \n¿Ya hiciste los pasos para redimir tu bono?\n1. Sí\n2. No"

    elif state == "WAITING_BONUS_RESOLVED":
        if msg == "1":
            reply = "¡Perfecto! Gracias por participar en nuestro estudio. Esperamos contar contigo en futuras investigaciones. ¡Hasta luego!"
            db.delete(session)
        elif msg == "2":
            reply = "Por favor, busca en tus chats de WhatsApp si tienes un mensaje nuestro de la cuenta de 'Súperincentivos' y sigue los pasos que están en ese chat.\n\nDespués de revisar, ¿pudiste resolverlo?\n1. Sí pude\n2. No pude"
            session.state = "WAITING_BONUS_SUPERINCENTIVOS"
        else:
            reply = "⚠️ Responde con 1 (Sí) o 2 (No)."

    elif state == "WAITING_BONUS_SUPERINCENTIVOS":
        if msg == "1":
            reply = "¡Excelente! Muchas gracias por participar. ¡Hasta luego!"
            db.delete(session)
        elif msg == "2":
            reply = "Entendido. Voy a escribirle a un agente humano y nos estaremos comunicando contigo a la brevedad posible para ayudarte. ¡Gracias por tu paciencia!"
            
            n_phone = phone[2:] if phone.startswith("57") and len(phone) == 12 else phone
            name_sql = text("SELECT person_name FROM calls WHERE phone_number = :p OR phone_number = :np LIMIT 1")
            name_rec = db_users.execute(name_sql, {"p": phone, "np": n_phone}).first()
            resp_name = name_rec.person_name if (name_rec and name_rec.person_name) else "Usuario Sin Nombre"
            
            alert_msg = f"🚨 *Alerta de Súperincentivos*\n\nUna persona intentó redimir su bono pero reporta que NO pudo resolver el proceso (vio el video y buscó el chat).\n\n👤 *Nombre (BD):* {resp_name}\n📞 *Soporte a:* {phone}\n📅 *Fecha:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            send_whatsapp_message("573136623816", alert_msg)
            
            db.delete(session)
        else:
            reply = "⚠️ Responde con 1 (Sí) o 2 (No)."

    elif state == "UNKNOWN_MENU":
        if msg == "1":
            reply = "Por favor, escribe el NÚMERO DE CELULAR (10 dígitos) del cual deseas consultar el estado de tu incentivo o bono:"
            session.state = "WAITING_BOND_PHONE"
        elif msg == "2":
            reply = "¡Gracias por estar interesado en participar en un estudio de investigación de mercados! Por favor, regálame TU NÚMERO DE CELULAR (10 dígitos):"
            session.state = "WAITING_REFERRAL_PHONE"
        else:
            reply = "⚠️ Opción inválida.\n1. Ver estado de un bono/incentivo\n2. Referir a un amig@ para un estudio"

    elif state == "WAITING_BOND_PHONE":
        bond_phone = "".join(filter(str.isdigit, msg))
        if len(bond_phone) >= 10:
            if bond_phone.startswith("57") and len(bond_phone) == 12:
                bond_phone = bond_phone[2:]
            
            calls_sql = text("SELECT study_id FROM calls WHERE phone_number = :p")
            call_records = db_users.execute(calls_sql, {"p": bond_phone}).fetchall()
            study_ids = [r.study_id for r in call_records if r.study_id]
            
            if not study_ids:
                reply = "Ese número no está registrado en nuestros estudios o bases recientes. Gracias por comunicarte, ¡hasta luego!"
                db.delete(session)
            else:
                placeholders = ','.join([':p' + str(i) for i in range(len(study_ids))])
                params = {f"p{i}": sid for i, sid in enumerate(study_ids)}
                studies_sql = text(f"SELECT is_active, status, created_at FROM studies WHERE id IN ({placeholders})")
                studies_records = db_users.execute(studies_sql, params).fetchall()
                
                has_open = False
                has_closed = False
                closed_dates = []
                for sr in studies_records:
                    if (sr.is_active == 0) or (str(sr.status).lower() == 'cerrado'):
                        has_closed = True
                        if sr.created_at: closed_dates.append(sr.created_at.strftime("%Y-%m-%d"))
                    else:
                        has_open = True
                        
                if has_open and not has_closed:
                    reply = "Tu participación ha sido registrada. Por el momento no se ha enviado la base de súperincentivos, en algunos días que cierre el estudio y luego de 15 días te llegará el proceso para que lo redimas. ¡Gracias por participar en nuestro estudio!"
                    db.delete(session)
                else:
                    date_str = closed_dates[0] if closed_dates else "recientemente"
                    reply = f"El estudio en el que participaste fue cerrado el {date_str}. Te debería llegar un mensaje de súperincentivos.\n\n¿Ya hiciste los pasos para redimir tu bono?\n1. Sí\n2. No"
                    session.state = "WAITING_BONUS_REDEEM_ANSWER"
        else:
            reply = "⚠️ Por favor escribe un número válido de al menos 10 dígitos."

    elif state == "WAITING_REFERRAL_PHONE":
        ref_phone = "".join(filter(str.isdigit, msg))
        if len(ref_phone) >= 10:
            if ref_phone.startswith("57") and len(ref_phone) == 12:
                ref_phone = ref_phone[2:]
                
            six_months_ago = datetime.now() - timedelta(days=180)
            calls_sql = text("SELECT id FROM calls WHERE phone_number = :p AND created_at >= :d")
            recent_call = db_users.execute(calls_sql, {"p": ref_phone, "d": six_months_ago}).first()
            
            if recent_call:
                reply = "Gracias, pero vemos que ya participaste en un estudio con nosotros en los últimos 6 meses. Por el momento no podemos registrarte de nuevo. ¡Hasta luego!"
                db.delete(session)
            else:
                ctx["ref_phone"] = ref_phone
                reply = "¡Perfecto! ¿Cuál es tu Nombre y Apellido completo?"
                session.state = "WAITING_REFERRAL_NAME"
        else:
            reply = "⚠️ Por favor escribe un número válido de al menos 10 dígitos."

    elif state == "WAITING_REFERRAL_NAME":
        ctx["ref_name"] = message_raw.strip()
        reply = "Gracias. Selecciona tu Género:\n1. Masculino\n2. Femenino\n3. Otro\n4. Prefiero no decir"
        session.state = "WAITING_REFERRAL_GENDER"

    elif state == "WAITING_REFERRAL_GENDER":
        mapping = {"1": "Masculino", "2": "Femenino", "3": "Otro", "4": "Prefiero no decir"}
        if msg in mapping:
            ctx["ref_gender"] = mapping[msg]
            reply = "¿Qué edad tienes? (Escribe el número, por ejemplo: 25)"
            session.state = "WAITING_REFERRAL_AGE"
        else:
            reply = "⚠️ Responde con el número de la opción (1 al 4):\n1. Masculino\n2. Femenino\n3. Otro\n4. Prefiero no decir"

    elif state == "WAITING_REFERRAL_AGE":
        if msg.isdigit() and 10 <= int(msg) <= 100:
            ctx["ref_age"] = int(msg)
            reply = "¿En qué ciudad resides?\n1. Bogotá\n2. Barranquilla\n3. Cali\n4. Medellín\n5. Bucaramanga\n6. Otra"
            session.state = "WAITING_REFERRAL_CITY"
        else:
            reply = "⚠️ Escribe tu edad en números (ejemplo: 30)."

    elif state == "WAITING_REFERRAL_CITY":
        mapping = {"1": "Bogotá", "2": "Barranquilla", "3": "Cali", "4": "Medellín", "5": "Bucaramanga"}
        if msg in mapping:
            ctx["ref_city"] = mapping[msg]
            reply = "¿En qué barrio vives?"
            session.state = "WAITING_REFERRAL_NEIGHBORHOOD"
        elif msg == "6":
            reply = "¿En qué otra ciudad vives? (Escríbela brevemente):"
            session.state = "WAITING_REFERRAL_CITY_OTHER"
        else:
            reply = "⚠️ Responde con el número de la opción (1 al 6)."

    elif state == "WAITING_REFERRAL_CITY_OTHER":
        ctx["ref_city"] = message_raw.strip()
        reply = "¿En qué barrio vives?"
        session.state = "WAITING_REFERRAL_NEIGHBORHOOD"

    elif state == "WAITING_REFERRAL_NEIGHBORHOOD":
        ctx["ref_neighborhood"] = message_raw.strip()
        reply = "¿Cuál es tu dirección de residencia?"
        session.state = "WAITING_REFERRAL_ADDRESS"

    elif state == "WAITING_REFERRAL_ADDRESS":
        ctx["ref_address"] = message_raw.strip()
        reply = "De acuerdo con la ley de protección de datos de Colombia, ¿Autorizas voluntariamente que AZ Marketing conserve estos datos para ser contactado en futuros estudios?\n1. Sí, acepto\n2. No acepto"
        session.state = "WAITING_REFERRAL_CONSENT"

    elif state == "WAITING_REFERRAL_CONSENT":
        if msg == "1" or msg == "si":
            referral = models.BotReferral(
                referral_phone=ctx.get("ref_phone"),
                referrer_phone=phone,
                full_name=ctx.get("ref_name"),
                gender=ctx.get("ref_gender"),
                age=ctx.get("ref_age"),
                city=ctx.get("ref_city"),
                neighborhood=ctx.get("ref_neighborhood"),
                address=ctx.get("ref_address"),
                consent=True
            )
            db.add(referral)
            db.commit()
            reply = "¡Tus datos han sido registrados con éxito! Muchas gracias por tu tiempo, te contactaremos cuando tengamos un estudio adecuado para tu perfil. ¡Hasta luego!"
            db.delete(session)
        elif msg == "2" or msg == "no":
            reply = "Entendido, no guardaremos tus datos. ¡Gracias por comunicarte con AZ Marketing, hasta luego!"
            db.delete(session)
        else:
            reply = "⚠️ Por favor responde 1 para Aceptar, o 2 para Rechazar."

    session.context_data = json.dumps(ctx)
    db.commit()
    
    # Log everything in BotQuotaUpdate
    log = models.BotQuotaUpdate(
        study_code=ctx.get("study_code", ""),
        phone_number=phone,
        message_text=message_raw,
        parsed_updates=reply.replace('\n', ' | ')
    )
    db.add(log)
    db.commit()
    
    # Send actual WhatsApp message if it's a real phone number
    if phone != "0000":
        send_whatsapp_message(phone, reply)
    
    return reply


def build_study_report(db, study_code):
    from sqlalchemy import func
    from datetime import datetime, date
    import json
    
    today = date.today()
    start_of_day = datetime(today.year, today.month, today.day)
    
    all_study_quotas = db.query(models.BotQuota).filter(models.BotQuota.study_code == study_code).all()
    quota_ids = [q.id for q in all_study_quotas]
    
    matrix_msg = f"📊 *Estado General: {study_code.upper()}*\n"
    
    grouped_quotas = {}
    for q in all_study_quotas:
        parts = q.category.split(' | ') if '|' in q.category else [q.category]
        parts.append(q.value)
        path_tuple = tuple(p.strip() for p in parts if p.strip())
        
        if not path_tuple:
            continue
        first_node = path_tuple[0]
        rest = " | ".join(path_tuple[1:])
        if first_node not in grouped_quotas:
            grouped_quotas[first_node] = []
        
        grouped_quotas[first_node].append(f"  {rest}: {q.current_count}/{q.target_count}")
    
    for group_name, lines in grouped_quotas.items():
        matrix_msg += f"\n*{group_name}*\n"
        matrix_msg += "\n".join(lines)
        
    daily_stats = db.query(
        models.QuotaSubmission.phone_number,
        func.count(models.QuotaSubmission.id)
    ).filter(
        models.QuotaSubmission.bot_quota_id.in_(quota_ids),
        models.QuotaSubmission.is_deleted == 0,
        models.QuotaSubmission.submitted_at >= start_of_day
    ).group_by(models.QuotaSubmission.phone_number).all()
    
    stats_msg = "\n\n📈 *Rendimiento Hoy:*\n"
    total_today = 0
    for p_num, count in daily_stats:
        stats_msg += f"📞 {p_num}: {count} encuestas\n"
        total_today += count
    
    if total_today == 0:
        stats_msg += "No hay encuestas hoy aún."
    else:
        stats_msg += f"Total hoy: {total_today}"
        
    return f"\n{matrix_msg}\n{stats_msg}"

def compute_next_bot_step(db, ctx, phone=""):

    study_code = ctx["study_code"]
    selected_path = ctx["selected_path"]
    
    quotas = db.query(models.BotQuota).filter(models.BotQuota.study_code == study_code).all()
    
    # Build array of full paths for all quotas
    valid_paths = []
    quota_map = {}
    for q in quotas:
        if q.category == "General":
            parts = [q.value]
        else:
            parts = [x.strip() for x in q.category.split("|")] + [q.value.strip()]
        valid_paths.append(parts)
        quota_map[tuple(parts)] = q
        
    # Filter paths that match selected_path prefix
    matched_paths = [p for p in valid_paths if p[:len(selected_path)] == selected_path]
    
    if not matched_paths:
        return "⚠️ Error interno: Las opciones que elegiste no conectan con una cuota válida. Escribe 'cancelar' e intenta de nuevo.", "IDLE"
        
    depth = len(selected_path)
    
    # Are we at the leaf?
    # If all matched_paths have length == depth, we hit the exact quota!
    if len(matched_paths) == 1 and len(matched_paths[0]) == depth:
        exact_path = tuple(matched_paths[0])
        quota = quota_map[exact_path]
        
        # Save submission
        sub = models.QuotaSubmission(
            bot_quota_id=quota.id,
            phone_number=phone,
            is_deleted=0
        )
        db.add(sub)
        quota.current_count += 1
        
        report = build_study_report(db, study_code)
        
        base_reply = f"✅ ¡Guardado! Faltan {quota.target_count - quota.current_count} encuestas de esta cuota."
        return f"{base_reply}{report}", "IDLE"
        
    # Not a leaf, gather next layer options
    next_options = []
    for p in matched_paths:
        if len(p) > depth:
            if p[depth] not in next_options:
                next_options.append(p[depth])
                
    if not next_options:
        return "⚠️ Error al conseguir la siguiente categoría.", "IDLE"
        
    ctx["current_options"] = next_options
    opts = "\n".join([f"{i+1}. {o}" for i, o in enumerate(next_options)])
    return f"Selecciona una opción:\n{opts}", "WAITING_CATEGORY"
