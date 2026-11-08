"""Cierre diario de campo por WhatsApp.

La persona que cargo al menos una encuesta hoy (hora Colombia) recibe la opcion
"Cerrar dia" en su menu. Al elegirla, el bot recorre a su gente asignada en el
estudio y por cada una pregunta: censos (que tipo y cuantos), transporte (monto
libre, solo si no hubo censos) e incentivo (monto). Al final guarda el cierre y
manda un resumen al supervisor y a los superusuarios.

Sin calculo de plata: se guarda lo declarado y lo que tiene el sistema.
"""
import re
from datetime import datetime, timedelta

from . import models

COLOMBIA_OFFSET_HOURS = 5

STATES = (
    "WAITING_CLOSING_STUDY",
    "WAITING_CLOSING_CENSOS",
    "WAITING_CLOSING_CENSUS_TYPE",
    "WAITING_CLOSING_CENSUS_QTY",
    "WAITING_CLOSING_CENSUS_MORE",
    "WAITING_CLOSING_TRANSPORT",
    "WAITING_CLOSING_INCENTIVE",
    "WAITING_CLOSING_INCENTIVE_AMOUNT",
)

CENSUS_TYPES = ["Censo", "Censo 2-3", "Censo 4"]
CENSUS_KEYS = {"censo": "generic", "censo 2-3": "c23", "censo 4": "c4"}
CENSUS_LABELS = {"generic": "censo", "c23": "censo 2-3", "c4": "censo 4"}

YES = ("1", "si", "sí", "s", "yes", "y", "claro")
NO = ("2", "no", "n")

MAX_LIST = 10


# --------------------------------------------------------------------------- #
# Utilidades
# --------------------------------------------------------------------------- #

def colombia_now():
    return datetime.utcnow() - timedelta(hours=COLOMBIA_OFFSET_HOURS)


def today_iso():
    return colombia_now().strftime("%Y-%m-%d")


def phone_variants(phone):
    phone = (phone or "").strip()
    if not phone:
        return []
    variants = [phone]
    if phone.startswith("57") and len(phone) > 10:
        variants.append(phone[2:])
    elif len(phone) == 10:
        variants.append("57" + phone)
    return variants


def name_key(value):
    import unicodedata
    normalized = unicodedata.normalize("NFKD", value or "")
    return normalized.encode("ascii", "ignore").decode().strip().lower()


def parse_int(text):
    """Acepta '5000', '5.000', '5,000', '$ 5.000'."""
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else None


def _buttons(reply, options, list_button="Elegir", section="Opciones"):
    if len(options) <= 3:
        return {
            "type": "button",
            "body": {"text": reply},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": str(i + 1), "title": str(opt)[:20]}}
                    for i, opt in enumerate(options)
                ]
            },
        }
    rows = [{"id": str(i + 1), "title": str(opt)[:24]} for i, opt in enumerate(options[:MAX_LIST])]
    return {
        "type": "list",
        "body": {"text": reply},
        "action": {
            "button": list_button,
            "sections": [{"title": section, "rows": rows}],
        },
    }


def _yes_no(reply):
    return _buttons(reply, ["Si", "No"])


# --------------------------------------------------------------------------- #
# Lectura del dia
# --------------------------------------------------------------------------- #

def today_submissions(db, phone):
    """Submissions de hoy (hora Colombia) hechas por este telefono."""
    variants = phone_variants(phone)
    if not variants:
        return []
    rows = db.query(models.QuotaSubmission).filter(
        models.QuotaSubmission.phone_number.in_(variants),
        models.QuotaSubmission.is_deleted == 0,
    ).all()
    day = today_iso()
    today = []
    for row in rows:
        moment = row.submitted_at
        if not moment:
            continue
        local = moment - timedelta(hours=COLOMBIA_OFFSET_HOURS)
        if local.strftime("%Y-%m-%d") == day:
            today.append(row)
    return today


def studies_with_activity(db, phone):
    subs = today_submissions(db, phone)
    if not subs:
        return []
    quota_ids = [s.bot_quota_id for s in subs if s.bot_quota_id]
    quotas = {
        q.id: q for q in db.query(models.BotQuota).filter(models.BotQuota.id.in_(quota_ids)).all()
    } if quota_ids else {}
    studies = []
    for sub in subs:
        quota = quotas.get(sub.bot_quota_id)
        code = (quota.study_code if quota else "") or ""
        if code and code not in studies:
            studies.append(code)
    return studies


def has_activity_today(db, phone):
    return bool(today_submissions(db, phone))


def roster_people(db, phone, study_code, fallback_name):
    """Gente asignada a este supervisor en este estudio.

    Si no hay nadie asignado, el supervisor se cierra a si mismo para no dejar
    el dia sin reportar.
    """
    variants = phone_variants(phone)
    rows = db.query(models.BotAgentInterviewer).filter(
        models.BotAgentInterviewer.agent_phone.in_(variants)
    ).order_by(models.BotAgentInterviewer.id).all()
    wanted = (study_code or "").strip().lower()
    people = []
    seen = set()
    for row in rows:
        if (row.study_code or "").strip().lower() != wanted:
            continue
        key = name_key(row.interviewer_name)
        if not key or key in seen:
            continue
        seen.add(key)
        people.append(row.interviewer_name.strip())
    if not people:
        people = [(fallback_name or "").strip() or phone]
    return people


def surveys_for(db, phone, study_code, person_name, is_self):
    """Encuestas que el sistema tiene registradas de esa persona hoy."""
    subs = today_submissions(db, phone)
    if not subs:
        return 0
    quota_ids = [s.bot_quota_id for s in subs if s.bot_quota_id]
    quotas = {
        q.id: q for q in db.query(models.BotQuota).filter(models.BotQuota.id.in_(quota_ids)).all()
    } if quota_ids else {}
    wanted = (study_code or "").strip().lower()
    key = name_key(person_name)
    total = 0
    for sub in subs:
        quota = quotas.get(sub.bot_quota_id)
        if not quota or (quota.study_code or "").strip().lower() != wanted:
            continue
        stored = (sub.interviewer_name or "").strip()
        if stored:
            if name_key(stored) == key:
                total += 1
        elif is_self:
            # Registros viejos sin encuestador: se le atribuyen al que carga.
            total += 1
    return total


# --------------------------------------------------------------------------- #
# Flujo
# --------------------------------------------------------------------------- #

def start(db, ctx, phone, sender_name):
    studies = studies_with_activity(db, phone)
    if not studies:
        return "No registraste encuestas hoy, asi que no hay nada que cerrar.", "IDLE", None, ctx

    ctx["closing"] = {"studies": studies, "filled_by": phone}
    if len(studies) > 1:
        reply = "¿Que estudio vas a cerrar?"
        return reply, "WAITING_CLOSING_STUDY", _buttons(reply, studies, "Elegir estudio", "Estudios"), ctx

    return _begin_study(db, ctx, phone, sender_name, studies[0])


def _begin_study(db, ctx, phone, sender_name, study_code):
    people = roster_people(db, phone, study_code, sender_name)
    ctx["closing"].update({
        "study": study_code,
        "people": people,
        "index": 0,
        "lines": [],
        "current": _blank_line(people[0], 0),
    })
    return _ask_censos(ctx)


def _blank_line(person, index):
    return {
        "name": person,
        "index": index,
        "censos": {},
        "transport": None,
        "incentive": None,
    }


def _ask_censos(ctx):
    current = ctx["closing"]["current"]
    reply = f"*{current['name']}*\n¿Tiene censos el estudio?"
    return reply, "WAITING_CLOSING_CENSOS", _yes_no(reply), ctx


def _ask_census_type(ctx):
    reply = "¿Que censo fue?"
    return reply, "WAITING_CLOSING_CENSUS_TYPE", _buttons(reply, CENSUS_TYPES, "Elegir", "Censos"), ctx


def _ask_census_qty(ctx):
    label = ctx["closing"]["current"].get("type_label", "censo")
    reply = f"¿Cuantos {label}?"
    return reply, "WAITING_CLOSING_CENSUS_QTY", None, ctx


def _ask_more_census(ctx):
    reply = "¿Otro tipo de censo?"
    return reply, "WAITING_CLOSING_CENSUS_MORE", _yes_no(reply), ctx


def _ask_transport(ctx):
    reply = "¿Cuanto de transporte? (0 si no tuvo)"
    return reply, "WAITING_CLOSING_TRANSPORT", None, ctx


def _ask_incentive(ctx):
    reply = "¿Tuvo incentivo?"
    return reply, "WAITING_CLOSING_INCENTIVE", _yes_no(reply), ctx


def _ask_incentive_amount(ctx):
    reply = "¿Cuanto de incentivo?"
    return reply, "WAITING_CLOSING_INCENTIVE_AMOUNT", None, ctx


def _finish_person(db, ctx, phone, sender_name):
    closing = ctx["closing"]
    closing["lines"].append(closing["current"])
    closing["index"] += 1
    if closing["index"] < len(closing["people"]):
        closing["current"] = _blank_line(closing["people"][closing["index"]], closing["index"])
        return _ask_censos(ctx)

    return _save_and_summary(db, ctx, phone, sender_name)


def _save_and_summary(db, ctx, phone, sender_name):
    closing = ctx["closing"]
    day = today_iso()
    study = closing["study"]
    variants = phone_variants(phone)

    existing = db.query(models.BotDailyClosing).filter(
        models.BotDailyClosing.close_date == day,
        models.BotDailyClosing.study_code == study,
        models.BotDailyClosing.supervisor_phone.in_(variants),
    ).first()

    if existing:
        record = existing
        db.query(models.BotDailyClosingLine).filter(
            models.BotDailyClosingLine.closing_id == record.id
        ).delete(synchronize_session=False)
        updated = True
    else:
        record = models.BotDailyClosing(
            close_date=day,
            study_code=study,
            supervisor_phone=phone,
            supervisor_name=sender_name or phone,
            filled_by=phone,
        )
        db.add(record)
        db.flush()
        updated = False

    for line in closing["lines"]:
        surveys = surveys_for(db, phone, study, line["name"], line["index"] == 0)
        line["surveys"] = surveys
        db.add(models.BotDailyClosingLine(
            closing_id=record.id,
            interviewer_name=line["name"],
            surveys_system=surveys,
            census_generic=line["censos"].get("generic", 0),
            census_23=line["censos"].get("c23", 0),
            census_4=line["censos"].get("c4", 0),
            transport_amount=line["transport"] or 0,
            incentive_amount=line["incentive"] or 0,
        ))

    db.commit()

    summary = build_summary(record, closing["lines"], day, study, updated)
    ctx["closing_summary"] = summary
    ctx.pop("closing", None)
    return summary, "IDLE", None, ctx


def build_summary(record, lines, day, study, updated):
    pretty_day = "/".join(reversed(day.split("-")))
    title = "Cierre del dia actualizado" if updated else "Cierre del dia"
    blocks = [f"*{title}* — {pretty_day}", f"Estudio {study}", ""]

    total_surveys = total_censos = total_transport = total_incentive = 0
    for line in lines:
        censos = line["censos"]
        census_total = censos.get("generic", 0) + censos.get("c23", 0) + censos.get("c4", 0)
        surveys = line.get("surveys", 0)
        parts = [f"{surveys} encuestas" if surveys != 1 else "1 encuesta"]
        censos_txt = []
        if censos.get("generic"):
            censos_txt.append(f"{censos['generic']} censo")
        if censos.get("c23"):
            censos_txt.append(f"{censos['c23']} censo 2-3")
        if censos.get("c4"):
            censos_txt.append(f"{censos['c4']} censo 4")
        if censos_txt:
            parts.append(", ".join(censos_txt))
        if line["transport"]:
            parts.append(f"transporte {line['transport']:,}".replace(",", "."))
        if line["incentive"]:
            parts.append(f"incentivo {line['incentive']:,}".replace(",", "."))
        total_surveys += surveys
        total_censos += census_total
        total_transport += line["transport"] or 0
        total_incentive += line["incentive"] or 0

        blocks.append(f"*{line['name']}*")
        blocks.append(" · ".join(parts))
        blocks.append("")

    blocks.append(
        "TOTAL: {} encuestas · {} censos · transporte {} · incentivo {}".format(
            total_surveys,
            total_censos,
            f"{total_transport:,}".replace(",", "."),
            f"{total_incentive:,}".replace(",", "."),
        )
    )
    return "\n".join(blocks).strip()


# --------------------------------------------------------------------------- #
# Dispatcher
# --------------------------------------------------------------------------- #

def handle(db, state, msg, ctx, phone, sender_name):
    closing = ctx.get("closing") or {}
    current = closing.get("current") or {}

    if state == "WAITING_CLOSING_STUDY":
        studies = closing.get("studies", [])
        choice = parse_int(msg)
        if choice and 1 <= choice <= len(studies):
            return _begin_study(db, ctx, phone, sender_name, studies[choice - 1])
        return "Elegi una opcion de la lista.", state, _buttons("¿Que estudio vas a cerrar?", studies), ctx

    if state == "WAITING_CLOSING_CENSOS":
        if msg in YES:
            return _ask_census_type(ctx)
        if msg in NO:
            return _ask_transport(ctx)
        return "Responde Si o No.", state, _yes_no(f"*{current.get('name', '')}*\n¿Tiene censos el estudio?"), ctx

    if state == "WAITING_CLOSING_CENSUS_TYPE":
        choice = parse_int(msg)
        if not choice or not (1 <= choice <= len(CENSUS_TYPES)):
            return "Elegi un tipo de censo.", state, _buttons("¿Que censo fue?", CENSUS_TYPES), ctx
        label = CENSUS_TYPES[choice - 1]
        current["type_key"] = CENSUS_KEYS[label.lower()]
        current["type_label"] = label.lower()
        return _ask_census_qty(ctx)

    if state == "WAITING_CLOSING_CENSUS_QTY":
        amount = parse_int(msg)
        if amount is None:
            return "Escribi un numero.", state, None, ctx
        key = current.get("type_key", "generic")
        current["censos"][key] = current["censos"].get(key, 0) + amount
        return _ask_more_census(ctx)

    if state == "WAITING_CLOSING_CENSUS_MORE":
        if msg in YES:
            return _ask_census_type(ctx)
        if msg in NO:
            # Si declaro censos, no se le pregunta transporte.
            if current.get("censos"):
                return _ask_incentive(ctx)
            return _ask_transport(ctx)
        return "Responde Si o No.", state, _yes_no("¿Otro tipo de censo?"), ctx

    if state == "WAITING_CLOSING_TRANSPORT":
        amount = parse_int(msg)
        if amount is None:
            return "Escribi un monto (0 si no tuvo).", state, None, ctx
        current["transport"] = amount
        return _ask_incentive(ctx)

    if state == "WAITING_CLOSING_INCENTIVE":
        if msg in YES:
            return _ask_incentive_amount(ctx)
        if msg in NO:
            current["incentive"] = 0
            return _finish_person(db, ctx, phone, sender_name)
        return "Responde Si o No.", state, _yes_no("¿Tuvo incentivo?"), ctx

    if state == "WAITING_CLOSING_INCENTIVE_AMOUNT":
        amount = parse_int(msg)
        if amount is None:
            return "Escribi un monto.", state, None, ctx
        current["incentive"] = amount
        return _finish_person(db, ctx, phone, sender_name)

    return "Se perdio el cierre del dia. Escribe 'Hola' para empezar de nuevo.", "IDLE", None, {}
