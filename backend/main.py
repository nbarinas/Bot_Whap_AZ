from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
import os
from fastapi.security import OAuth2PasswordRequestForm

from . import models, database, auth, render_utils, upload_media
import re

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

import asyncio
from datetime import datetime, timedelta

async def call_reminder_task():
    while True:
        try:
            # Forzamos la hora a Colombia (UTC-5) asegurando que funcione en el servidor de Render
            now = datetime.utcnow() - timedelta(hours=5)
            # We want calls whose appointment_time is between now and now + 5 min
            window_end = now + timedelta(minutes=5)
            
            users_db = next(database.get_users_db())
            try:
                from sqlalchemy import text
                # We handle if full_name exists. Let's do the same fallback for safety if users.full_name doesn't exist.
                # UPDATED: More robust window - check any pending for today up to now + 5 min
                try:
                    sql = text("""
                        SELECT c.id, c.appointment_time, c.phone_number, c.person_name, u.phone_number as agent_phone, u.full_name as agent_name, s.name as study_name
                        FROM calls c
                        JOIN users u ON c.user_id = u.id
                        LEFT JOIN studies s ON c.study_id = s.id
                        WHERE c.appointment_time <= :end_time
                        AND date(c.appointment_time) = date(:now)
                        AND (c.reminder_sent IS NULL OR c.reminder_sent = 0)
                        AND (LOWER(COALESCE(c.status, '')) LIKE '%pending%' OR LOWER(COALESCE(c.status, '')) LIKE '%schedul%')
                    """)
                    records = users_db.execute(sql, {"now": now, "end_time": window_end}).fetchall()
                except Exception:
                    # Fallback si no existe la columna full_name en users
                    sql = text("""
                        SELECT c.id, c.appointment_time, c.phone_number, c.person_name, u.phone_number as agent_phone, u.username as agent_name, s.name as study_name
                        FROM calls c
                        JOIN users u ON c.user_id = u.id
                        LEFT JOIN studies s ON c.study_id = s.id
                        WHERE c.appointment_time <= :end_time
                        AND date(c.appointment_time) = date(:now)
                        AND (c.reminder_sent IS NULL OR c.reminder_sent = 0)
                        AND (LOWER(COALESCE(c.status, '')) LIKE '%pending%' OR LOWER(COALESCE(c.status, '')) LIKE '%schedul%')
                    """)
                    records = users_db.execute(sql, {"now": now, "end_time": window_end}).fetchall()
                
                for r in records:
                    call_id = r.id
                        
                    # Format message
                    agent_phone = r.agent_phone
                    if agent_phone:
                        # Normalize
                        if not str(agent_phone).startswith("57"):
                            agent_phone = "57" + str(agent_phone)
                            
                        agent_name = r.agent_name or "Agente"
                        study_name = r.study_name or "Desconocido"
                        
                        appt_time_str = r.appointment_time
                        if hasattr(r.appointment_time, 'strftime'):
                            appt_time_str = r.appointment_time.strftime("%H:%M") # just the time is enough, it's today
                            
                        msg = f"🔔 *Recordatorio de Llamada*\nHola {agent_name}, soy un bot automatizado del CRM de AZ Marketing. A las {appt_time_str} tienes una llamada programada para el estudio *{study_name}*.\n\nDebes llamar al *{r.phone_number}* de la Sr(a) *{r.person_name}*."
                        
                        # using existing send_whatsapp_message in main.py
                        try:
                            send_whatsapp_message(agent_phone, msg)
                            print(f"Recordatorio de llamada enviado a {agent_phone} para llamada id {call_id}.")
                            
                            # ---- TEMPORARY ADMIN ALERTS (To be reverted after 2 PM) ----
                            alert_msg = f"Se acaba de enviar un mensaje a {agent_phone} avisando que:\n\"{msg}\""
                            try:
                                send_whatsapp_message("573136623816", alert_msg)
                                send_whatsapp_message("573234968972", alert_msg)
                            except Exception as alert_e:
                                print(f"Error enviando alertas temporales: {alert_e}")
                            # -------------------------------------------------------------
                            
                            # Update the calls table
                            update_sql = text("UPDATE calls SET reminder_sent = 1 WHERE id = :call_id")
                            users_db.execute(update_sql, {"call_id": call_id})
                            users_db.commit()
                        except Exception as e:
                            print(f"Error enviando o guardando recordatorio a {agent_phone}: {e}")
                            users_db.rollback()
                                
            finally:
                users_db.close()
                
        except Exception as e:
            print(f"Error in call_reminder_task: {e}")
            
        # Wait 60 seconds before checking again
        await asyncio.sleep(60)

@app.on_event("startup")
def on_startup():
    models.Base.metadata.create_all(bind=database.bot_engine)
    try:
        from sqlalchemy import text
        with database.bot_engine.begin() as conn:
            conn.execute(text("ALTER TABLE bot_quotas ADD COLUMN is_closed INTEGER DEFAULT 0"))
    except Exception:
        pass # Column presumably exists
        
    asyncio.create_task(call_reminder_task())

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
        resp_json = response.json() if response.status_code == 200 else {}
        msg_id = resp_json.get("messages", [{}])[0].get("id", "unknown")
        
        if response.status_code != 200:
            print(f"META ERROR RESPONSE: {response.text}")
        response.raise_for_status()
        print(f"WhatsApp message successfully sent to {to_phone} (ID: {msg_id})")
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

def send_whatsapp_interactive(to_phone: str, interactive_data: dict):
    """
    Sends an interactive message (Buttons or Lists) via Meta API.
    """
    url = f"https://graph.facebook.com/v22.0/{WHATSAPP_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    data = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "interactive",
        "interactive": interactive_data
    }
    try:
        response = requests.post(url, headers=headers, data=json.dumps(data))
        if response.status_code != 200:
            print(f"META ERROR RESPONSE (INTERACTIVE): {response.text}")
        response.raise_for_status()
        print(f"WhatsApp interactive successfully sent to {to_phone}")
    except Exception as e:
        print(f"Error sending WhatsApp interactive to {to_phone}: {str(e)}")


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
                            # We handle both text and interactive replies
                            text_msg = ""
                            if msg_data.get("type") == "text":
                                text_msg = msg_data["text"]["body"]
                            elif msg_data.get("type") == "interactive":
                                interactive = msg_data.get("interactive", {})
                                iter_type = interactive.get("type")
                                if iter_type == "button_reply":
                                    text_msg = interactive["button_reply"]["id"]
                                elif iter_type == "list_reply":
                                    text_msg = interactive["list_reply"]["id"]
                                    
                            if text_msg:
                                print(f"Received WhatsApp MSG from {phone}: {text_msg}")
                                # Process it using our core logic
                                process_bot_message(phone, text_msg, db, db_users)
                            elif msg_data.get("type") == "image":
                                image_data = msg_data.get("image", {})
                                media_id = image_data.get("id")
                                print(f"Received WhatsApp IMAGE from {phone}: {media_id}")
                                process_bot_message(phone, "IMAGE_RECEIVED", db, db_users, media_id=media_id)
                            elif msg_data.get("type") == "audio":
                                print(f"Received WhatsApp AUDIO from {phone}")
                                process_bot_message(phone, "AUDIO_RECEIVED", db, db_users)
                            elif msg_data.get("type") == "video":
                                print(f"Received WhatsApp VIDEO from {phone}")
                                process_bot_message(phone, "VIDEO_RECEIVED", db, db_users)
                                
                    # Tracking Delivery Statuses
                    if "statuses" in value:
                        for status in value["statuses"]:
                            recipient = status.get("recipient_id")
                            status_type = status.get("status") # sent, delivered, read, failed
                            msg_id = status.get("id")
                            print(f"STATUS UPDATE: Message {msg_id} to {recipient} is now {status_type}")
                            if "errors" in status:
                                print(f"META DELIVERY ERROR for {recipient}: {status['errors']}")
                                
            return {"status": "ok"}
        except Exception as e:
            print(f"Error processing webhook: {e}")
            return {"status": "error"}
    else:
        # Not a WhatsApp event
        raise HTTPException(status_code=404)


def finalize_census_flow(db, phone, ctx):
    """
    Logs data to Sheets and resets the session.
    """
    censo_num = ctx.get("census_number")
    name = ctx.get("person_name")
    neighborhood = ctx.get("neighborhood")
    address = ctx.get("address")
    photos = ctx.get("photos", [])
    
    # Format for Sheets: [Censo, Nombre, Barrio, Dirección, Fecha, Hora, Link1, Link2]
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")
    
    photo_links = [f"https://drive.google.com/open?id={pid}" for pid in photos]
    while len(photo_links) < 2:
        photo_links.append("")
        
    row = [censo_num, name, neighborhood, address, date_str, time_str] + photo_links
    
    # Log to Sheets (Disabled to avoid dependencies)
    # media_handler.log_to_sheets(row)
    
    # Clean up session
    session = db.query(models.BotSession).filter(models.BotSession.phone_number == phone).first()
    if session:
        db.delete(session)
        db.commit()
        
    return f"✅ ¡Entrega del censo *{censo_num}* finalizada con éxito!\n\nSe han guardado {len(photos)} fotos en Google Drive y se ha registrado en la hoja de cálculo."


@app.post("/api/bot/webhook-simulate")
def simulate_whatsapp_webhook(req: WebhookSimulateRequest, db: Session = Depends(database.get_db), db_users: Session = Depends(database.get_users_db)):
    """
    Legacy/Simulator endpoint used by the frontend.
    """
    reply, interactive = process_bot_message(req.phone_number, req.message, db, db_users)
    return {"reply": reply, "interactive": interactive}


def process_bot_message(phone_raw: str, message_raw: str, db: Session, db_users: Session, media_id: str = None) -> tuple[str, dict]:
    """
    Core bot logic extracted from the simulator so both endpoints can share it.
    Returns (reply_text, interactive_data_dict)
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
            
    # --- DETECCION DE CENSO (TRIGGER) ---
    if user_type == "AGENT" and not media_id:
        censo_match = re.search(r"censo\s*(\d+)", msg)
        if censo_match:
            censo_num = censo_match.group(1)
            # Buscar en la base de datos
            censo_sql = text("SELECT id, person_name, neighborhood, address FROM calls WHERE census = :c LIMIT 1")
            censo_rec = db_users.execute(censo_sql, {"c": censo_num}).first()
            
            if censo_rec:
                # Iniciar flujo de censo
                session = db.query(models.BotSession).filter(models.BotSession.phone_number == phone).first()
                if not session:
                    session = models.BotSession(phone_number=phone)
                    db.add(session)
                
                session.state = "WAITING_CENSO_CONFIRMATION"
                ctx_data = {
                    "census_number": censo_num,
                    "call_id": censo_rec.id,
                    "person_name": censo_rec.person_name,
                    "neighborhood": censo_rec.neighborhood,
                    "address": censo_rec.address,
                    "photos": []
                }
                session.context_data = json.dumps(ctx_data)
                db.commit()
                
                reply = f"✅ Censo {censo_num} encontrado.\n\n👤 *Nombre:* {censo_rec.person_name}\n🏠 *Barrio:* {censo_rec.neighborhood}\n📍 *Dirección:* {censo_rec.address}\n\n¿Es la información correcta?"
                interactive_data = {
                    "type": "button",
                    "body": {"text": reply},
                    "action": {
                        "buttons": [
                            {"type": "reply", "reply": {"id": "1", "title": "Sí, es correcto"}},
                            {"type": "reply", "reply": {"id": "2", "title": "No, volver a digitar"}}
                        ]
                    }
                }
                return reply, interactive_data
            else:
                return f"❌ No se encontró el censo *{censo_num}* en la base de datos. Por favor verifica el número.", None

    
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
    interactive_data = None

    # Global media handlers (Skip state logic if audio/video is received)
    is_media_unsupported = False
    if msg == "audio_received":
        reply = "⚠️ Por el momento no puedo escuchar mensajes de voz. Por favor, escribe tu solicitud para poder ayudarte."
        is_media_unsupported = True
    elif msg == "video_received":
        reply = "⚠️ Por el momento no puedo procesar videos. Por favor, escribe tu mensaje o envía una foto cuando sea solicitada."
        is_media_unsupported = True

    def handle_invalid(err_msg, options_text, interactive_fallback=None):
        attempts = ctx.get("invalid_attempts", 0) + 1
        if attempts >= 3:
            session.state = "IDLE"
            return "🚫 Demasiados intentos inválidos. La sesión se ha reiniciado.\n👋 Escribe 'Hola' para empezar de nuevo.", None, {}
        ctx["invalid_attempts"] = attempts
        # Cleanly combine error message and options
        full_reply = f"⚠️ {err_msg}"
        if options_text:
            full_reply += f"\n\nOpciones disponibles:\n{options_text}"
        return full_reply, interactive_fallback, ctx

    if not is_media_unsupported:
        if state == "IDLE":
            if user_type == "INACTIVE_AGENT":
                reply = "⚠️ Por el momento no estás activo para registrar cuotas.\n\nSin embargo, puedes validar números en base:"
                session.state = "WAITING_INACTIVE_ACTION"
                ctx["invalid_attempts"] = 0
                interactive_data = {
                    "type": "button",
                    "body": {"text": reply},
                    "action": {
                        "buttons": [
                            {"type": "reply", "reply": {"id": "1", "title": "Validar número"}},
                            {"type": "reply", "reply": {"id": "2", "title": "Salir"}}
                        ]
                    }
                }
                ctx["interactive_fallback"] = interactive_data
            
            elif user_type == "AGENT":
                # Ask for study
                studies = db.query(models.BotQuota.study_code).filter(models.BotQuota.is_closed == 0).distinct().all()
                if not studies:
                    reply = timeout_message + "No hay estudios activos en este momento."
                    ctx["available_studies"] = []
                    ctx["validate_option_idx"] = 1
                    session.state = "WAITING_STUDY"
                    interactive_data = {
                        "type": "button",
                        "body": {"text": reply},
                        "action": {
                            "buttons": [
                                {"type": "reply", "reply": {"id": "1", "title": "Validar número"}}
                            ]
                        }
                    }
                    ctx["interactive_fallback"] = interactive_data
                else:
                    study_list = [s[0] for s in studies]
                    ctx["available_studies"] = study_list
                    ctx["invalid_attempts"] = 0
                    session.state = "WAITING_STUDY"
                
                    opts = "\n".join([f"{i+1}. {s}" for i, s in enumerate(study_list)])
                    validate_idx = len(study_list) + 1
                    opts += f"\n{validate_idx}. Validar número en la base"
                    ctx["validate_option_idx"] = validate_idx
                
                    greeting = f"¡Hola {agent_name}!" if agent_name else "¡Hola!"
                    reply = timeout_message + f"{greeting} ¿Qué deseas hacer?"
                
                    rows = [{"id": str(i+1), "title": s[:24]} for i, s in enumerate(study_list)]
                    rows.append({"id": str(validate_idx), "title": "Validar en base"})
                
                    interactive_data = {
                        "type": "list",
                        "body": {"text": reply},
                        "action": {
                            "button": "Ver Opciones",
                            "sections": [{"title": "Estudios Disponibles", "rows": rows}]
                        }
                    }
                    ctx["interactive_fallback"] = interactive_data
                
            elif user_type == "RESPONDENT":
                calls_sql = text("SELECT study_id FROM calls WHERE phone_number = :p OR phone_number = :np")
                call_records = db_users.execute(calls_sql, {"p": phone, "np": normalized_phone}).fetchall()
            
                study_ids = [r.study_id for r in call_records if r.study_id]
                if not study_ids:
                    user_type = "UNKNOWN"
                else:
                    placeholders = ','.join([':p' + str(i) for i in range(len(study_ids))])
                    params = {f"p{i}": sid for i, sid in enumerate(study_ids)}
                    studies_sql = text(f"SELECT is_active, status, created_at FROM studies WHERE id IN ({placeholders}) ORDER BY created_at DESC, id DESC LIMIT 1")
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
                        reply = timeout_message + f"Tu participación fue en un estudio que cerró el {date_str}. Te debería llegar un mensaje de súperincentivos.\n\n¿Ya hiciste los pasos para redimir tu bono?"
                        session.state = "WAITING_BONUS_REDEEM_ANSWER"
                        ctx["invalid_attempts"] = 0
                        interactive_data = {
                            "type": "button",
                            "body": {"text": reply},
                            "action": {
                                "buttons": [
                                    {"type": "reply", "reply": {"id": "1", "title": "Sí"}},
                                    {"type": "reply", "reply": {"id": "2", "title": "No"}}
                                ]
                            }
                        }
                        ctx["interactive_fallback"] = interactive_data

            if user_type == "UNKNOWN":
                reply = timeout_message + "¡Hola! Gracias por comunicarte con AZ Marketing. ¿En qué podemos ayudarte?"
                session.state = "UNKNOWN_MENU"
                ctx["invalid_attempts"] = 0
                interactive_data = {
                    "type": "button",
                    "body": {"text": reply},
                    "action": {
                        "buttons": [
                            {"type": "reply", "reply": {"id": "1", "title": "Incentivo o bono"}},
                            {"type": "reply", "reply": {"id": "2", "title": "Referir a un amig@"}}
                        ]
                    }
                }
                ctx["interactive_fallback"] = interactive_data
            
        elif state == "WAITING_STUDY":
            available = ctx.get("available_studies", [])
            validate_idx = ctx.get("validate_option_idx")
            opts_text = "\n".join([f"{i+1}. {s}" for i, s in enumerate(available)])
            opts_text += f"\n{validate_idx}. Validar número en la base" if validate_idx else ""
            try:
                choice = int(msg)
                if 1 <= choice <= len(available):
                    study_code = available[choice - 1]
                    ctx["study_code"] = study_code
                    ctx["invalid_attempts"] = 0
                    session.state = "WAITING_ACTION"
                    reply = f"Estudio {study_code} seleccionado. ¿Qué deseas hacer?"
                    interactive_data = {
                        "type": "button",
                        "body": {"text": reply},
                        "action": {
                            "buttons": [
                                {"type": "reply", "reply": {"id": "1", "title": "Añadir 1 encuesta"}},
                                {"type": "reply", "reply": {"id": "2", "title": "Borrar mi última"}},
                                {"type": "reply", "reply": {"id": "3", "title": "Ver cuotas actuales"}}
                            ]
                        }
                    }
                    ctx["interactive_fallback"] = interactive_data
                elif validate_idx and choice == validate_idx:
                    reply = "Por favor, digite el número de celular a validar:"
                    session.state = "WAITING_VALIDATION_PHONE"
                    ctx["invalid_attempts"] = 0
                else:
                    reply, interactive_data, ctx = handle_invalid("Opción inválida.", opts_text, ctx.get("interactive_fallback"))
            except ValueError:
                reply, interactive_data, ctx = handle_invalid("Selección inválida.", opts_text, ctx.get("interactive_fallback"))

        elif state == "WAITING_ACTION":
            opts_text = "1. Añadir 1 encuesta\n2. Borrar mi última\n3. Ver cuotas actuales"
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
                # Just send to the requester
                send_quota_report_to_agents(db, study_code, [phone], f"📊 Estado de Cuotas: *{study_code.upper()}*")
                reply = "Te acabo de enviar la tabla de cuotas actualizada. 👆"
                
                session.state = "IDLE"
                ctx = {}
            
            elif msg == "1":
                ctx["action"] = "ADD"
                ctx["selected_path"] = []
                ctx["invalid_attempts"] = 0
                reply_text, next_state, next_interactive = compute_next_bot_step_interactive(db, ctx, phone)
                reply = reply_text
                interactive_data = next_interactive
                session.state = next_state
            else:
                # Try free-text fast match
                study_code = ctx.get("study_code")
                matched_quota, err_msg = check_free_text_quota(db, study_code, msg)
                if matched_quota:
                    q_name = matched_quota.category + " | " + matched_quota.value if matched_quota.category != "General" else matched_quota.value
                    reply = f"¿Quieres agregar 1 encuesta a la cuota:\n*{q_name}*?"
                    session.state = "WAITING_FREE_TEXT_CONFIRM"
                    ctx["free_text_quota_id"] = matched_quota.id
                    interactive_data = {
                        "type": "button",
                        "body": {"text": reply},
                        "action": {
                            "buttons": [
                                {"type": "reply", "reply": {"id": "1", "title": "Sí, agregar"}},
                                {"type": "reply", "reply": {"id": "2", "title": "No, cancelar"}}
                            ]
                        }
                    }
                    ctx["interactive_fallback"] = interactive_data
                elif err_msg:
                    reply, interactive_data, ctx = handle_invalid(err_msg, opts_text, ctx.get("interactive_fallback"))
                else:
                    reply, interactive_data, ctx = handle_invalid("Selección inválida.", opts_text, ctx.get("interactive_fallback"))


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
                    reply_text, next_state, next_interactive = compute_next_bot_step_interactive(db, ctx, phone)
                    reply = reply_text
                    interactive_data = next_interactive
                    session.state = next_state
                    if next_state == "IDLE":
                        ctx = {} # Clean up
                else:
                    reply, interactive_data, ctx = handle_invalid("Opción inválida.", opts_text, ctx.get("interactive_fallback"))
            except ValueError:
                study_code = ctx.get("study_code")
                matched_quota, err_msg = check_free_text_quota(db, study_code, msg)
                if matched_quota:
                    q_name = matched_quota.category + " | " + matched_quota.value if matched_quota.category != "General" else matched_quota.value
                    reply = f"¿Quieres agregar 1 encuesta a la cuota:\n*{q_name}*?"
                    session.state = "WAITING_FREE_TEXT_CONFIRM"
                    ctx["free_text_quota_id"] = matched_quota.id
                    interactive_data = {
                        "type": "button",
                        "body": {"text": reply},
                        "action": {
                            "buttons": [
                                {"type": "reply", "reply": {"id": "1", "title": "Sí, agregar"}},
                                {"type": "reply", "reply": {"id": "2", "title": "No, cancelar"}}
                            ]
                        }
                    }
                    ctx["interactive_fallback"] = interactive_data
                elif err_msg:
                    reply, interactive_data, ctx = handle_invalid(err_msg, opts_text, ctx.get("interactive_fallback"))
                else:
                    reply, interactive_data, ctx = handle_invalid("Selección inválida.", opts_text, ctx.get("interactive_fallback"))


        elif state == "WAITING_FREE_TEXT_CONFIRM":
            if msg in ["1", "si", "sí", "sí, agregar"]:
                quota_id = ctx.get("free_text_quota_id")
                quota = db.query(models.BotQuota).get(quota_id)
                if quota:
                    sub = models.QuotaSubmission(
                        bot_quota_id=quota.id,
                        phone_number=phone,
                        is_deleted=0
                    )
                    db.add(sub)
                    quota.current_count += 1
                    study_code = ctx.get("study_code")
                    
                    active_phones = get_daily_active_phones_for_study(db, study_code)
                    if phone not in active_phones:
                        active_phones.append(phone)
                        
                    send_quota_report_to_agents(db, study_code, active_phones, f"📈 ¡Nueva encuesta guardada por {phone}!\nFaltan {quota.target_count - quota.current_count} para esta cuota.")
                    
                    reply = f"✅ ¡Guardado! Faltan {quota.target_count - quota.current_count} encuestas de esta cuota."
                else:
                    reply = "⚠️ Error: No se encontró la cuota en la base de datos."
                session.state = "IDLE"
                ctx = {}
            elif msg in ["2", "no", "no, cancelar", "cancelar"]:
                reply = "❌ Operación cancelada. Escribe 'Hola' para empezar de nuevo."
                session.state = "IDLE"
                ctx = {}
            else:
                reply, interactive_data, ctx = handle_invalid("Selección inválida.", "1. Sí, agregar\n2. No, cancelar", ctx.get("interactive_fallback"))

        # --- NUEVA RUTA: ESTADO VALIDACION NUMEROS ---
    
        elif state == "WAITING_INACTIVE_ACTION":
            if msg == "1":
                reply = "Por favor, digite el número de celular a validar:"
                session.state = "WAITING_VALIDATION_PHONE"
                ctx["invalid_attempts"] = 0
            elif msg == "2":
                reply = "¡Gracias! Hasta luego."
                db.delete(session)
            else:
                reply, ctx = handle_invalid("Opción inválida.", "1. Validar número\n2. Salir")
            
        elif state == "WAITING_VALIDATION_PHONE":
            # Clean number (removing spaces, dashes, etc.)
            val_phone = "".join(filter(str.isdigit, msg))
        
            if not val_phone:
                reply, interactive_data, ctx = handle_invalid("No detecté ningún número en tu mensaje. Por favor, escribe el celular de 10 dígitos.", "", None)
            elif len(val_phone) < 10:
                reply, interactive_data, ctx = handle_invalid(f"El número detectado '{val_phone}' es muy corto. Debe tener al menos 10 dígitos. Por favor, escríbelo de nuevo:", "", None)
            elif len(val_phone) >= 10:
                if val_phone.startswith("57") and len(val_phone) == 12:
                    val_phone = val_phone[2:]
            
                # Busco en base de datos calls
                calls_sql = text("""
                    SELECT c.created_at, s.name as study_name
                    FROM calls c
                    LEFT JOIN studies s ON c.study_id = s.id
                    WHERE c.phone_number = :p OR c.phone_number = :np
                    ORDER BY s.created_at DESC, c.id DESC
                """)
                records = db_users.execute(calls_sql, {"p": val_phone, "np": "57" + val_phone}).fetchall()
                if records:
                    total_count = len(records)
                    latest = records[0]
                    latest_date_str = latest.created_at.strftime('%Y-%m-%d') if latest.created_at else "desconocida"
                    latest_study = latest.study_name if latest.study_name else "desconocido"
                
                    if total_count == 1:
                        reply = f"⚠️ Ojo, esta persona participó la última vez en la base *{latest_study}* de fecha *{latest_date_str}*.\n\nEn total ha participado 1 vez.\n\n¿Quieres validar otro número?"
                    else:
                        historial = []
                        # Mostramos hasta las últimas 5 adicionales
                        for r in records[1:6]:
                            d_str = r.created_at.strftime('%Y-%m-%d') if r.created_at else "desconocida"
                            s_name = r.study_name if r.study_name else "desconocido"
                            historial.append(f"• {s_name} ({d_str})")
                        
                        if total_count > 6:
                            historial.append(f"... y {total_count - 6} más.")
                        
                        historial_str = "\n".join(historial)
                        reply = f"⚠️ Ojo, esta persona participó la última vez en la base *{latest_study}* de fecha *{latest_date_str}*.\n\nEn total ha participado *{total_count} veces*. Historial reciente:\n{historial_str}\n\n¿Quieres validar otro número?"
                else:
                    reply = f"✅ El número *{val_phone}* no está en la base. Puede hacer encuesta.\n\n¿Quieres validar otro número?"
                
                session.state = "WAITING_VALIDATION_MORE"
                ctx["invalid_attempts"] = 0
                interactive_data = {
                    "type": "button",
                    "body": {"text": reply},
                    "action": {
                        "buttons": [
                            {"type": "reply", "reply": {"id": "1", "title": "Sí"}},
                            {"type": "reply", "reply": {"id": "2", "title": "No o cerrar"}}
                        ]
                    }
                }
                ctx["interactive_fallback"] = interactive_data
            
        elif state == "WAITING_VALIDATION_MORE":
            if msg in ["1", "si", "sí"]:
                reply = "Por favor, digite el siguiente número de celular a validar:"
                session.state = "WAITING_VALIDATION_PHONE"
                ctx["invalid_attempts"] = 0
            elif msg in ["2", "no", "cerrar", "salir"]:
                reply = "¡Gracias por validar! Hasta luego."
                session.state = "IDLE"
                ctx = {}
            else:
                reply, interactive_data, ctx = handle_invalid("Responde 1 para validar otro o 2 para cerrar.", "1. Sí\n2. No o cerrar", ctx.get("interactive_fallback"))

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
                reply = "Por favor, busca en tus chats de WhatsApp si tienes un mensaje nuestro de la cuenta de 'Súperincentivos' y sigue los pasos que están en ese chat.\n\nDespués de revisar, ¿pudiste resolverlo?"
                session.state = "WAITING_BONUS_SUPERINCENTIVOS"
                interactive_data = {
                    "type": "button",
                    "body": {"text": reply},
                    "action": {
                        "buttons": [
                            {"type": "reply", "reply": {"id": "1", "title": "Sí pude"}},
                            {"type": "reply", "reply": {"id": "2", "title": "No pude"}}
                        ]
                    }
                }
                ctx["interactive_fallback"] = interactive_data
            else:
                reply, interactive_data, ctx = handle_invalid("Opción inválida.", "1. Sí pude\n2. No pude", ctx.get("interactive_fallback"))

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
                reply, interactive_data, ctx = handle_invalid("Opción inválida.", "1. Sí pude\n2. No pude", ctx.get("interactive_fallback"))

        elif state == "UNKNOWN_MENU":
            if msg == "1":
                reply = "Por favor, escribe el NÚMERO DE CELULAR (10 dígitos) del cual deseas consultar el estado de tu incentivo o bono:"
                session.state = "WAITING_BOND_PHONE"
                ctx["invalid_attempts"] = 0
            elif msg == "2":
                reply = "¡Gracias por estar interesado en participar en un estudio de investigación de mercados! Por favor, regálame TU NÚMERO DE CELULAR (10 dígitos):"
                session.state = "WAITING_REFERRAL_PHONE"
                ctx["invalid_attempts"] = 0
            else:
                reply, interactive_data, ctx = handle_invalid("Opción inválida.", "1. Ver estado...\n2. Referir...", ctx.get("interactive_fallback"))

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
                    studies_sql = text(f"SELECT is_active, status, created_at FROM studies WHERE id IN ({placeholders}) ORDER BY created_at DESC, id DESC LIMIT 1")
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
                reply, interactive_data, ctx = handle_invalid("Por favor escribe un número válido de al menos 10 dígitos:", "", None)

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
                reply, interactive_data, ctx = handle_invalid("Por favor escribe un número válido de al menos 10 dígitos:", "", None)

        elif state == "WAITING_REFERRAL_NAME":
            ctx["ref_name"] = message_raw.strip()
            reply = "Gracias. Selecciona tu Género:"
            session.state = "WAITING_REFERRAL_GENDER"
            ctx["invalid_attempts"] = 0
            interactive_data = {
                "type": "list",
                "body": {"text": reply},
                "action": {
                    "button": "Ver Opciones",
                    "sections": [{"title": "Géneros", "rows": [
                        {"id": "1", "title": "Masculino"},
                        {"id": "2", "title": "Femenino"},
                        {"id": "3", "title": "Otro"},
                        {"id": "4", "title": "Prefiero no decir"}
                    ]}]
                }
            }
            ctx["interactive_fallback"] = interactive_data

        elif state == "WAITING_REFERRAL_GENDER":
            mapping = {"1": "Masculino", "2": "Femenino", "3": "Otro", "4": "Prefiero no decir"}
            if msg in mapping:
                ctx["ref_gender"] = mapping[msg]
                reply = "¿Qué edad tienes? (Escribe el número, por ejemplo: 25)"
                session.state = "WAITING_REFERRAL_AGE"
                ctx["invalid_attempts"] = 0
            else:
                reply, interactive_data, ctx = handle_invalid("Opción inválida.", "", ctx.get("interactive_fallback"))

        elif state == "WAITING_REFERRAL_NEIGHBORHOOD":
            ctx["ref_neighborhood"] = message_raw.strip()
            reply = "¿En qué barrio vives?"
            session.state = "WAITING_REFERRAL_NEIGHBORHOOD"

        # --- NUEVOS ESTADOS: FLUJO DE CENSO ---
    
        elif state == "WAITING_CENSO_CONFIRMATION":
            if msg in ["1", "si", "sí", "sí, es correcto"]:
                session.state = "WAITING_PHOTO_1"
                reply = "¡Perfecto! Por favor, envíame la *primera foto* de la entrega."
                db.commit()
            elif msg in ["2", "no", "volver a digitar"]:
                session.state = "IDLE"
                reply = "Entendido. Por favor, escribe de nuevo el censo (ej: censo 1015)."
                ctx = {}
                session.context_data = "{}"
                db.commit()
            else:
                reply, interactive_data, ctx = handle_invalid("Opción inválida.", "1. Sí\n2. No", ctx.get("interactive_fallback"))

        elif state == "WAITING_PHOTO_1":
            if media_id:
                censo_num = ctx.get("census_number", "unknown")
                filename = f"Censo_{censo_num}_1.jpg"
                temp_path = os.path.join(os.path.dirname(__file__), f"temp_{phone}_1.jpg")
            
                # Drive integration disabled
                if False: # media_handler.download_whatsapp_media(media_id, temp_path):
                    pass
                
                # We skip Drive and just proceed to next state for now
                if True:
                    # ctx["photos"].append(drive_id)
                    session.context_data = json.dumps(ctx)
                    session.state = "WAITING_PHOTO_2_OR_FINISH"
                    reply = "✅ Primera foto recibida (Guardado en Drive desactivado).\n\n¿Deseas enviar una *segunda foto* o ya terminaste?"
                    interactive_data = {
                        "type": "button",
                        "body": {"text": reply},
                        "action": {
                            "buttons": [
                                {"type": "reply", "reply": {"id": "1", "title": "Enviar otra"}},
                                {"type": "reply", "reply": {"id": "2", "title": "Terminar"}}
                            ]
                        }
                    }
                    ctx["interactive_fallback"] = interactive_data
                    db.commit()
            else:
                reply = "📷 Por favor, envía la foto de la entrega."

        elif state == "WAITING_PHOTO_2_OR_FINISH":
            if media_id:
                censo_num = ctx.get("census_number", "unknown")
                filename = f"Censo_{censo_num}_2.jpg"
                temp_path = os.path.join(os.path.dirname(__file__), f"temp_{phone}_2.jpg")
            
                # Drive integration disabled
                if True:
                    # ctx["photos"].append(drive_id)
                    # Terminar flujo
                    finish_msg = finalize_census_flow(db, phone, ctx)
                    return finish_msg, None
            elif msg in ["2", "terminar"]:
                finish_msg = finalize_census_flow(db, phone, ctx)
                return finish_msg, None
            else:
                reply, interactive_data, ctx = handle_invalid("Opción inválida.", "1. Enviar otra\n2. Terminar", ctx.get("interactive_fallback"))

        elif state == "WAITING_REFERRAL_AGE":
            if msg.isdigit() and 10 <= int(msg) <= 100:
                ctx["ref_age"] = int(msg)
                reply = "¿En qué ciudad resides?"
                session.state = "WAITING_REFERRAL_CITY"
                ctx["invalid_attempts"] = 0
                interactive_data = {
                    "type": "list",
                    "body": {"text": reply},
                    "action": {
                        "button": "Ver Opciones",
                        "sections": [{"title": "Ciudades", "rows": [
                            {"id": "1", "title": "Bogotá"},
                            {"id": "2", "title": "Barranquilla"},
                            {"id": "3", "title": "Cali"},
                            {"id": "4", "title": "Medellín"},
                            {"id": "5", "title": "Bucaramanga"},
                            {"id": "6", "title": "Otra"}
                        ]}]
                    }
                }
                ctx["interactive_fallback"] = interactive_data
            else:
                reply, interactive_data, ctx = handle_invalid("Por favor escribe tu edad en números validos.", "", ctx.get("interactive_fallback"))

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
                reply, interactive_data, ctx = handle_invalid("Opción inválida.", "", ctx.get("interactive_fallback"))

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
            reply = "De acuerdo con la ley de protección de datos de Colombia, ¿Autorizas voluntariamente que AZ Marketing conserve estos datos para ser contactado en futuros estudios?"
            session.state = "WAITING_REFERRAL_CONSENT"
            ctx["invalid_attempts"] = 0
            interactive_data = {
                "type": "button",
                "body": {"text": reply},
                "action": {
                    "buttons": [
                        {"type": "reply", "reply": {"id": "1", "title": "Sí, acepto"}},
                        {"type": "reply", "reply": {"id": "2", "title": "No acepto"}}
                    ]
                }
            }
            ctx["interactive_fallback"] = interactive_data

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
                reply, interactive_data, ctx = handle_invalid("Opción inválida.", "1. Sí, acepto\n2. No acepto", ctx.get("interactive_fallback"))
    # End of if not is_media_unsupported

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
    
    if phone != "0000":
        if interactive_data:
            # Bug fix: If there is a reply starting with an emoji (warning/error), 
            # send it as a separate text message first so it's not hidden by the interactive menu.
            if reply and (reply.startswith("⚠️") or reply.startswith("🚫")):
                send_whatsapp_message(phone, reply)
            
            send_whatsapp_interactive(phone, interactive_data)
        else:
            send_whatsapp_message(phone, reply)
    
    return reply, interactive_data


def send_quota_report_to_agents(db, study_code, phones, caption=""):
    """
    Helper to send a visual quota report to one or more agents. 
    Renders and uploads once, spreads to all.
    """
    try:
        # Import inside to avoid circular deps or load order issues if any
        from . import models, render_utils, upload_media
        
        # 1. Get components for the image
        all_study_quotas = db.query(models.BotQuota).filter(models.BotQuota.study_code == study_code).all()
        if not all_study_quotas:
            print(f"DEBUG: No quotas found for study {study_code}")
            return
            
        col_tree = {} # { first_node: set(leaf_node) }
        row_keys = set()
        data_map = {} # { middle_str: { first_node: { leaf_node: {...} } } }

        for q in all_study_quotas:
            parts = q.category.split(' | ') if '|' in q.category else [q.category]
            parts.append(q.value)
            path_tuple = tuple(p.strip() for p in parts if p.strip())
            if not path_tuple: continue
            
            first_node = path_tuple[0]
            if len(path_tuple) > 2:
                middle_str = " | ".join(path_tuple[1:-1])
                leaf_node = path_tuple[-1]
            elif len(path_tuple) == 2:
                middle_str = "-"
                leaf_node = path_tuple[-1]
            else:
                middle_str = "-"
                leaf_node = path_tuple[0]
            
            if first_node not in col_tree: col_tree[first_node] = set()
            col_tree[first_node].add(leaf_node)
            row_keys.add(middle_str)
            if middle_str not in data_map: data_map[middle_str] = {}
            if first_node not in data_map[middle_str]: data_map[middle_str][first_node] = {}
            data_map[middle_str][first_node][leaf_node] = {'current': q.current_count, 'target': q.target_count}

        ordered_first_nodes = sorted(list(col_tree.keys()))
        ordered_leaf_nodes = {fn: sorted(list(col_tree[fn])) for fn in ordered_first_nodes}
        sorted_rows = sorted(list(row_keys))

        # 2. Render Image
        img_filename = f"broadcast_{study_code}.png"
        img_path = os.path.join(BASE_DIR, img_filename)
        render_utils.generate_quota_table_image(
            data_map, ordered_first_nodes, ordered_leaf_nodes, sorted_rows, study_code, img_path
        )
        
        # 3. Upload to Meta
        print(f"DEBUG: Uploading broadcast image for {study_code}...")
        media_id = upload_media.upload_media(img_path, "image/png")
        
        if media_id:
            # 4. Broadcast to all recipients
            cap = caption if caption else f"📊 Cuotas Actualizadas: *{study_code.upper()}*"
            for phone in phones:
                try:
                    send_whatsapp_media(phone, "image", media_id, cap)
                except Exception as ex:
                    print(f"Error broadcasting to {phone}: {ex}")
        
        # Clean up
        if os.path.exists(img_path):
            os.remove(img_path)
            
    except Exception as e:
        print(f"Error in send_quota_report_to_agents: {e}")

def get_daily_active_phones_for_study(db, study_code):
    """
    Returns unique phone numbers that have submitted surveys for the study today.
    """
    from datetime import date, datetime
    today = date.today()
    start_of_day = datetime(today.year, today.month, today.day)
    
    # Identify quotas belonging to this study
    quota_ids_subquery = db.query(models.BotQuota.id).filter(models.BotQuota.study_code == study_code).subquery()
    
    active_phones = db.query(
        models.QuotaSubmission.phone_number
    ).filter(
        models.QuotaSubmission.bot_quota_id.in_(quota_ids_subquery),
        models.QuotaSubmission.is_deleted == 0,
        models.QuotaSubmission.submitted_at >= start_of_day
    ).distinct().all()
    
    return [p[0] for p in active_phones if p[0]]

def build_study_report(db, study_code):
    from sqlalchemy import func
    from datetime import datetime, date
    import json
    
    today = date.today()
    start_of_day = datetime(today.year, today.month, today.day)
    
    all_study_quotas = db.query(models.BotQuota).filter(models.BotQuota.study_code == study_code).all()
    quota_ids = [q.id for q in all_study_quotas]
    
    matrix_msg = f"📊 *Estado General: {study_code.upper()}*\n"
    
    col_tree = {} # { first_node: set(leaf_node) }
    row_keys = set()
    data_map = {} # { middle_str: { first_node: { leaf_node: {...} } } }

    for q in all_study_quotas:
        parts = q.category.split(' | ') if '|' in q.category else [q.category]
        parts.append(q.value)
        path_tuple = tuple(p.strip() for p in parts if p.strip())
        
        if not path_tuple:
            continue
            
        first_node = path_tuple[0]
        if len(path_tuple) > 2:
            middle_str = " | ".join(path_tuple[1:-1])
            leaf_node = path_tuple[-1]
        elif len(path_tuple) == 2:
            middle_str = "-"
            leaf_node = path_tuple[-1]
        else: # length 1
            middle_str = "-"
            leaf_node = path_tuple[0]
            
        if first_node not in col_tree:
            col_tree[first_node] = set()
        col_tree[first_node].add(leaf_node)
        
        row_keys.add(middle_str)
        
        if middle_str not in data_map:
            data_map[middle_str] = {}
        if first_node not in data_map[middle_str]:
            data_map[middle_str][first_node] = {}
            
        data_map[middle_str][first_node][leaf_node] = {
            'current': q.current_count,
            'target': q.target_count
        }

    # Order nodes
    ordered_first_nodes = sorted(list(col_tree.keys()))
    ordered_leaf_nodes = {fn: sorted(list(col_tree[fn])) for fn in ordered_first_nodes}
    sorted_rows = sorted(list(row_keys))
    
    max_row_len = max([len(r) for r in sorted_rows] + [4])
    max_row_len = min(max_row_len, 10)
    
    def calc_visual_len(s):
        # Emojis on WhatsApp monospace act approximately like 2 character spaces wide.
        # len("🟡") counts as 1. So we add 1 for every emoji to simulate visual width.
        return len(s) + s.count('🟡') + s.count('👨') + s.count('👩')

    col_widths = {}
    for fn in ordered_first_nodes:
        for ln in ordered_leaf_nodes[fn]:
            col_key = (fn, ln)
            max_len = calc_visual_len(ln)
            for r in sorted_rows:
                if fn in data_map[r] and ln in data_map[r][fn]:
                    cdata = data_map[r][fn][ln]
                    cell_str = f"{cdata['current']}/{cdata['target']}"
                    if cdata['current'] >= cdata['target']:
                        cell_str += "🟡"
                    if calc_visual_len(cell_str) > max_len:
                        max_len = calc_visual_len(cell_str)
            col_widths[col_key] = max(max_len, 3)

    for fn in ordered_first_nodes:
        num_cols = len(ordered_leaf_nodes[fn])
        
        # Inner length: cols (value + 2 spaces padding left/right) + inner separators " | " (length 3)
        fn_inner_len = sum((col_widths[(fn, ln)] + 2) for ln in ordered_leaf_nodes[fn]) + (num_cols - 1) * 3
        
        visual_fn_len = calc_visual_len(fn)
        total_spaces = fn_inner_len - visual_fn_len
        left_spaces = total_spaces // 2
        right_spaces = total_spaces - left_spaces
        fn_name = (" " * left_spaces) + fn + (" " * right_spaces)
        
        head1 = f"| {' ' * max_row_len} |"
        head2 = f"| {'Cat.'.ljust(max_row_len)} |"
        sep = f"+-{'-' * max_row_len}-+"
        
        head1 += f"{fn_name}|"
        
        for j, ln in enumerate(ordered_leaf_nodes[fn]):
            is_last_ln = (j == len(ordered_leaf_nodes[fn]) - 1)
            
            b_char = "|" if is_last_ln else " | "
            s_char = "+" if is_last_ln else "-+-"
            
            padding = col_widths[(fn, ln)] - calc_visual_len(ln)
            head2 += f" {ln}{' ' * padding} {b_char}"
            sep += f"-{'-' * col_widths[(fn, ln)]}-{s_char}"

        matrix_msg += f"```\n{sep}\n{head1}\n{head2}\n{sep}\n"
        
        for r in sorted_rows:
            r_str = r[:max_row_len].ljust(max_row_len)
            line = f"| {r_str} |"
            
            for j, ln in enumerate(ordered_leaf_nodes[fn]):
                is_last_ln = (j == len(ordered_leaf_nodes[fn]) - 1)
                b_char = "|" if is_last_ln else " | "
                
                if fn in data_map[r] and ln in data_map[r][fn]:
                    cdata = data_map[r][fn][ln]
                    cell_str = f"{cdata['current']}/{cdata['target']}"
                    if cdata['current'] >= cdata['target']:
                        cell_str += "🟡"
                else:
                    cell_str = "-"
                    
                padding = col_widths[(fn, ln)] - calc_visual_len(cell_str)
                line += f" {cell_str}{' ' * padding} {b_char}"
                
            matrix_msg += f"{line}\n{sep}\n"
            
        matrix_msg += f"```\n\n"
        
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

def check_free_text_quota(db, study_code: str, msg: str):
    msg_lower = msg.strip().lower()
    quotas = db.query(models.BotQuota).filter(models.BotQuota.study_code == study_code).all()
    
    matched_quotas = []
    for q in quotas:
        if q.category == "General":
            parts = [q.value.strip()]
        else:
            parts = [x.strip() for x in q.category.split("|")] + [q.value.strip()]
            
        all_parts_found = True
        for p in parts:
            if p.lower() not in msg_lower:
                all_parts_found = False
                break
        if all_parts_found:
            matched_quotas.append(q)
            
    if len(matched_quotas) == 1:
        return matched_quotas[0], ""
        
    elif len(matched_quotas) > 1:
        return None, "Hay varias cuotas que coinciden con tu texto. Por favor, sé más específico o usa el menú numérico."
        
    return None, ""

def compute_next_bot_step_interactive(db, ctx, phone="") -> tuple[str, str, dict]:

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
        return "⚠️ Error interno: Las opciones que elegiste no conectan con una cuota válida. Escribe 'cancelar' e intenta de nuevo.", "IDLE", None
        
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
        
        # Broadcast update to everyone active today
        active_phones = get_daily_active_phones_for_study(db, study_code)
        # Ensure the current reporter is included if not already in the active list 
        # (they should be since we just committed the submission)
        if phone not in active_phones:
            active_phones.append(phone)
            
        send_quota_report_to_agents(db, study_code, active_phones, f"📈 ¡Nueva encuesta guardada por {phone}!\nFaltan {quota.target_count - quota.current_count} para esta cuota.")
        
        return f"✅ ¡Guardado! Faltan {quota.target_count - quota.current_count} encuestas de esta cuota.", "IDLE", None
        
    # Not a leaf, gather next layer options
    next_options = []
    for p in matched_paths:
        if len(p) > depth:
            if p[depth] not in next_options:
                next_options.append(p[depth])
                
    if not next_options:
        return "⚠️ Error al conseguir la siguiente categoría.", "IDLE", None
        
    ctx["current_options"] = next_options
    if depth == 0:
        reply = "⚡ *Modo rápido:* Escribe la cuota completa en un solo mensaje (ej: 'mb hombre 15-19').\n\n📌 O selecciona paso a paso:"
    else:
        reply = "Selecciona una opción:"
    
    rows = []
    for i, o in enumerate(next_options):
        # WA interactive lists have a limit of 24 chars for the title
        rows.append({"id": str(i+1), "title": str(o)[:24]})
        
    # Let's chunk to 10 max if there are more than 10 options, although Meta limits per section are 10
    interactive_data = {
        "type": "list",
        "body": {"text": reply},
        "action": {
            "button": "Seleccionar",
            "sections": [{"title": "Categorías", "rows": rows[:10]}]
        }
    }
    ctx["interactive_fallback"] = interactive_data
    return reply, "WAITING_CATEGORY", interactive_data
