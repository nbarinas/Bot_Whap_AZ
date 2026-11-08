"""Tests del cierre diario por WhatsApp.

Ejecutar con:  python tests/day_closing_test.py

Cubre:
- El boton "Cerrar dia" solo aparece si hubo al menos una encuesta hoy (hora Colombia).
- Flujo completo: censos 2-3 + censo 4, transporte, incentivo, resumen al supervisor
  y al superusuario.
- Si hubo censos no se pregunta transporte; si no hubo, si se pregunta.
- Volver a cerrar el mismo dia sobrescribe, no suma.
- Una encuesta de ayer no cuenta como actividad de hoy.
"""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend import models
from backend.main import process_bot_message
import backend.main as main_module

PHONE = "3001234567"
SUPERUSER_PHONE = "3234968972"
STUDY = "ESTUDIO A"


def _noop(*args, **kwargs):
    return None


def setup_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    models.Base.metadata.create_all(bind=engine)
    models.UsersBase.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal()


def seed(db):
    """Supervisor con dos encuestadores asignados, superusuario y un estudio."""
    db.execute(text("""
        INSERT INTO users (username, hashed_password, role, phone_number)
        VALUES ('pepe', 'x', 'agent', :p),
               ('armando', 'x', 'superuser', :s)
    """), {"p": PHONE, "s": SUPERUSER_PHONE})
    db.add(models.BotActiveAgent(phone_number=PHONE, assigned_studies=STUDY))
    db.add(models.BotStudy(name=STUDY, study_type="STANDARD"))
    db.add(models.BotQuota(
        study_code=STUDY, category="Tipo de Punto", value="transporte",
        target_count=50, current_count=0, point_type="transporte",
    ))
    for name in ("Encuestador 1", "Encuestador 2"):
        db.add(models.BotAgentInterviewer(
            agent_phone=PHONE, study_code=STUDY, interviewer_name=name))
    db.commit()


def quota(db):
    return db.query(models.BotQuota).filter(models.BotQuota.study_code == STUDY).first()


def add_submission(db, interviewer, when=None, phone=PHONE):
    sub = models.QuotaSubmission(
        bot_quota_id=quota(db).id,
        phone_number=phone,
        interviewer_name=interviewer,
        is_deleted=0,
    )
    if when is not None:
        sub.submitted_at = when
    db.add(sub)
    db.commit()
    return sub


def _norm(value):
    import unicodedata
    return unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode().strip().lower()


def menu_option_index(reply, interactive, label="Cerrar día"):
    titles = []
    action = (interactive or {}).get("action", {})
    if "buttons" in action:
        titles = [b["reply"]["title"] for b in action["buttons"]]
    else:
        titles = [r["title"] for r in action.get("sections", [{}])[0].get("rows", [])]
    for idx, title in enumerate(titles, start=1):
        if _norm(title) == _norm(label):
            return idx
    return None


def captured_sends():
    sent = []

    def _capture(to_phone, message_text):
        sent.append((to_phone, message_text))

    main_module.send_whatsapp_message = _capture
    main_module.send_whatsapp_interactive = _noop
    main_module.send_quota_report_to_agents = _noop
    main_module.send_whatsapp_media = _noop
    return sent


def test_option_only_with_activity_today():
    """Sin encuestas de hoy no hay boton; con una de hoy aparece."""
    db = setup_db()
    seed(db)
    captured_sends()

    reply, interactive = process_bot_message(PHONE, "hola", db, db)
    assert menu_option_index(reply, interactive) is None, "No debe ofrecer cerrar dia sin actividad"

    add_submission(db, "Encuestador 1")
    reply, interactive = process_bot_message(PHONE, "hola", db, db)
    assert menu_option_index(reply, interactive) is not None, "Con actividad de hoy debe ofrecer cerrar dia"
    print("OK test_option_only_with_activity_today")


def test_full_closing_with_two_people():
    """Dos personas, censos de los dos tipos, transporte e incentivo."""
    db = setup_db()
    seed(db)
    sent = captured_sends()
    add_submission(db, "Encuestador 1")
    add_submission(db, "Encuestador 1")
    add_submission(db, "Encuestador 2")

    reply, interactive = process_bot_message(PHONE, "hola", db, db)
    closing_idx = menu_option_index(reply, interactive)
    reply, _ = process_bot_message(PHONE, str(closing_idx), db, db)
    assert "censos" in reply.lower() and "Encuestador 1" in reply, reply

    process_bot_message(PHONE, "1", db, db)      # si tuvo censos
    process_bot_message(PHONE, "2", db, db)      # censo 2-3
    process_bot_message(PHONE, "20", db, db)     # cantidad
    process_bot_message(PHONE, "1", db, db)      # otro tipo: si
    process_bot_message(PHONE, "3", db, db)      # censo 4
    process_bot_message(PHONE, "10", db, db)     # cantidad
    process_bot_message(PHONE, "2", db, db)      # otro tipo: no
    reply, _ = process_bot_message(PHONE, "1", db, db)   # incentivo: si
    assert "cuanto de incentivo" in reply.lower(), reply
    reply, _ = process_bot_message(PHONE, "5000", db, db)  # monto incentivo -> persona 2
    assert "Encuestador 2" in reply, reply

    process_bot_message(PHONE, "2", db, db)      # censos: no
    process_bot_message(PHONE, "7400", db, db)   # transporte
    reply, _ = process_bot_message(PHONE, "2", db, db)  # incentivo: no -> cierra

    closings = db.query(models.BotDailyClosing).all()
    assert len(closings) == 1, f"Esperaba 1 cierre, obtuve {len(closings)}"
    lines = db.query(models.BotDailyClosingLine).order_by(models.BotDailyClosingLine.id).all()
    assert len(lines) == 2, f"Esperaba 2 lineas, obtuve {len(lines)}"

    first, second = lines
    assert (first.interviewer_name, first.surveys_system) == ("Encuestador 1", 2), (first.interviewer_name, first.surveys_system)
    assert (first.census_23, first.census_4, first.transport_amount, first.incentive_amount) == (20, 10, 0, 5000), (
        first.census_23, first.census_4, first.transport_amount, first.incentive_amount)
    assert (second.interviewer_name, second.surveys_system) == ("Encuestador 2", 1), (second.interviewer_name, second.surveys_system)
    assert (second.transport_amount, second.incentive_amount) == (7400, 0), (second.transport_amount, second.incentive_amount)

    assert "2 encuestas" in reply and "1 encuesta" in reply, reply
    assert "20 censo 2-3" in reply and "10 censo 4" in reply, reply
    assert "transporte 7.400" in reply, reply
    assert "incentivo 5.000" in reply, reply

    superuser_msgs = [text for to_phone, text in sent if to_phone == "57" + SUPERUSER_PHONE]
    assert superuser_msgs, f"El superusuario no recibio el resumen: {sent}"
    assert "Cierre del dia" in superuser_msgs[-1], superuser_msgs[-1]
    print("OK test_full_closing_with_two_people")


def test_transport_only_without_censos():
    """Con censos no se pregunta transporte; sin censos si."""
    db = setup_db()
    seed(db)
    captured_sends()
    add_submission(db, "Encuestador 1")

    reply, interactive = process_bot_message(PHONE, "hola", db, db)
    process_bot_message(PHONE, str(menu_option_index(reply, interactive)), db, db)

    process_bot_message(PHONE, "1", db, db)   # censos: si
    process_bot_message(PHONE, "1", db, db)   # censo generico
    process_bot_message(PHONE, "5", db, db)   # cantidad
    reply, _ = process_bot_message(PHONE, "2", db, db)  # otro tipo: no
    assert "transporte" not in reply.lower(), f"No debe preguntar transporte si hubo censos: {reply}"
    assert "incentivo" in reply.lower(), reply

    # La segunda persona no tuvo censos: ahi si se pregunta transporte.
    process_bot_message(PHONE, "2", db, db)      # incentivo: no -> persona 2
    reply, _ = process_bot_message(PHONE, "2", db, db)  # censos: no
    assert "transporte" in reply.lower(), f"Sin censos debe preguntar transporte: {reply}"
    print("OK test_transport_only_without_censos")


def test_closing_twice_overwrites():
    """Cerrar de nuevo el mismo dia reemplaza las lineas, no las duplica."""
    db = setup_db()
    seed(db)
    captured_sends()
    add_submission(db, "Encuestador 1")

    for _ in range(2):
        reply, interactive = process_bot_message(PHONE, "hola", db, db)
        process_bot_message(PHONE, str(menu_option_index(reply, interactive)), db, db)
        process_bot_message(PHONE, "2", db, db)     # censos: no (persona 1)
        process_bot_message(PHONE, "0", db, db)     # transporte
        process_bot_message(PHONE, "2", db, db)     # incentivo: no
        process_bot_message(PHONE, "2", db, db)     # censos: no (persona 2)
        process_bot_message(PHONE, "0", db, db)     # transporte
        reply, _ = process_bot_message(PHONE, "2", db, db)  # incentivo: no -> cierra

    assert db.query(models.BotDailyClosing).count() == 1
    assert db.query(models.BotDailyClosingLine).count() == 2, "No debe duplicar lineas"
    assert "actualizado" in reply.lower(), reply
    print("OK test_closing_twice_overwrites")


def test_yesterday_does_not_count():
    """Una encuesta de ayer no habilita el cierre ni suma al dia."""
    db = setup_db()
    seed(db)
    captured_sends()
    yesterday = datetime.utcnow() - timedelta(days=1)
    add_submission(db, "Encuestador 1", when=yesterday)

    reply, interactive = process_bot_message(PHONE, "hola", db, db)
    assert menu_option_index(reply, interactive) is None, "Ayer no es actividad de hoy"

    add_submission(db, "Encuestador 1")
    reply, interactive = process_bot_message(PHONE, "hola", db, db)
    process_bot_message(PHONE, str(menu_option_index(reply, interactive)), db, db)
    process_bot_message(PHONE, "2", db, db)   # censos: no
    process_bot_message(PHONE, "0", db, db)   # transporte
    process_bot_message(PHONE, "2", db, db)   # incentivo: no
    process_bot_message(PHONE, "2", db, db)   # persona 2: censos no
    process_bot_message(PHONE, "0", db, db)   # transporte
    process_bot_message(PHONE, "2", db, db)   # incentivo no -> cierra

    first = db.query(models.BotDailyClosingLine).filter(
        models.BotDailyClosingLine.interviewer_name == "Encuestador 1").first()
    assert first.surveys_system == 1, f"Solo debe contar la de hoy: {first.surveys_system}"
    print("OK test_yesterday_does_not_count")


if __name__ == "__main__":
    test_option_only_with_activity_today()
    test_full_closing_with_two_people()
    test_transport_only_without_censos()
    test_closing_twice_overwrites()
    test_yesterday_does_not_count()
    print("\nTodos los tests del cierre diario pasaron")
