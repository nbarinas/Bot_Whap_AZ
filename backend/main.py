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
    models.Base.metadata.create_all(bind=database.engine)

@app.get("/")
def read_root():
    return FileResponse(os.path.join(FRONTEND_DIR, "quotas.html"))

@app.get("/login")
def login_page():
    return FileResponse(os.path.join(FRONTEND_DIR, "login.html"))

@app.post("/api/token")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(database.get_db)):
    user = db.query(models.User).filter(models.User.username == form_data.username).first()
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
            "current_count": q.current_count
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

class WebhookSimulateRequest(BaseModel):
    phone_number: str
    message: str

import re
import json
import requests
from sqlalchemy import text

# WhatsApp Configuration Constants (Use environment variables in production)
WHATSAPP_TOKEN = "EAAXs5LUMDHoBQ6fh0CDjwAgYPNQD5jDqzib5xgCAHPQ4XkTa0AMBAvNyCvLGZCnZCs5QAIGOQFLG4xDDUorTNsZA9ZAsk1wmUQyXQ6w0tdYrZCIDhQLarbrsjzt23OZAZAKAi2oFlmtxYDWlasB3jylqx1NlwUfsolJxFJaBPDdf1bvUvUKqzajoX0ZBKAgV80WUM26Qkh2caLRnTqZCyz4oziqZCuKN9g7RcfrTsppzSqI8Fl1UuzxfzZBd5067KbAeVnXAdtG3xxK6ZCYKuToc2gZDZD"
WHATSAPP_PHONE_ID = "933487246524604"
WHATSAPP_VERIFY_TOKEN = "azbot_secreto_2026"

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
        response.raise_for_status()
        print(f"WhatsApp message successfully sent to {to_phone}")
    except Exception as e:
        print(f"Error sending WhatsApp message to {to_phone}: {str(e)}")


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
async def receive_whatsapp_webhook(request: Request, db: Session = Depends(database.get_db)):
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
                                process_bot_message(phone, text_msg, db)
                                
            return {"status": "ok"}
        except Exception as e:
            print(f"Error processing webhook: {e}")
            return {"status": "error"}
    else:
        # Not a WhatsApp event
        raise HTTPException(status_code=404)


@app.post("/api/bot/webhook-simulate")
def simulate_whatsapp_webhook(req: WebhookSimulateRequest, db: Session = Depends(database.get_db)):
    """
    Legacy/Simulator endpoint used by the frontend.
    """
    reply = process_bot_message(req.phone_number, req.message, db)
    return {"reply": reply}


def process_bot_message(phone_raw: str, message_raw: str, db: Session) -> str:
    """
    Core bot logic extracted from the simulator so both endpoints can share it.
    """
    msg = message_raw.strip().lower()
    phone = phone_raw.strip()
    
    # 1. Authorize User for Quota Management
    sql = text("SELECT role FROM users WHERE phone_number = :p")
    user_record = db.execute(sql, {"p": phone}).first()
    
    is_authorized = bool(user_record) or phone == "0000"
    
    if not is_authorized:
        # Strict Validation: Only registered agents can use the bot
        reply = "🚫 Acceso denegado. Este número de teléfono no está autorizado como encuestador."
        
        # Log this interaction
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
        now = datetime.now(timezone.utc)
        session_time = session.updated_at
        if session_time.tzinfo is None:
            session_time = session_time.replace(tzinfo=timezone.utc)
            
        if now - session_time > timedelta(minutes=5):
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
        # Ask for study
        studies = db.query(models.BotQuota.study_code).distinct().all()
        if not studies:
            reply = timeout_message + "No hay estudios activos en este momento."
        else:
            study_list = [s[0] for s in studies]
            ctx["available_studies"] = study_list
            ctx["invalid_attempts"] = 0
            session.state = "WAITING_STUDY"
            
            opts = "\n".join([f"{i+1}. {s}" for i, s in enumerate(study_list)])
            reply = timeout_message + f"¡Hola! Selecciona el estudio en el que estás:\n{opts}"
            
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
