"""Tests de la Parte B: el bot pregunta con qué encuestador se registra la encuesta.

Ejecutar con:  python tests/interviewer_question_test.py

Cubre:
- Siempre pregunta, aunque la única opción sea el mismo que carga.
- No guarda nada hasta que se elige el encuestador.
- Ofrece al que carga primero y después el personal de ESE estudio (no el de otro).
- Una respuesta inválida no guarda nada.
- La ruta de texto libre también pasa por la pregunta.
- Con más de 10 opciones aparece "Ver más" y la segunda página también se puede elegir.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend import models
from backend.main import process_bot_message
import backend.main as main_module

PHONE = "3001234567"


def _noop(*args, **kwargs):
    return None


main_module.send_whatsapp_message = _noop
main_module.send_whatsapp_interactive = _noop
main_module.send_quota_report_to_agents = _noop
main_module.send_whatsapp_media = _noop


def setup_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    models.Base.metadata.create_all(bind=engine)
    models.UsersBase.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal()


def create_study(db, code="ESTUDIO A"):
    study = models.BotStudy(name=code, study_type="STANDARD")
    db.add(study)
    db.commit()
    db.refresh(study)
    db.add(models.BotQuota(
        study_id=study.id, study_code=code, category="Tipo de Punto", value="transporte",
        target_count=10, current_count=0, point_type="transporte",
    ))
    db.add(models.BotQuota(
        study_id=study.id, study_code=code, category="Hombre | 18-35", value="MB",
        target_count=10, current_count=0, point_type="General",
    ))
    db.commit()


def register_agent(db, phone=PHONE, studies="ESTUDIO A", username="pepe"):
    db.execute(text("""
        INSERT INTO users (username, hashed_password, role, phone_number)
        VALUES (:u, 'x', 'agent', :p)
    """), {"u": username, "p": phone})
    db.add(models.BotActiveAgent(phone_number=phone, assigned_studies=studies))
    db.commit()


def add_roster(db, names, phone=PHONE, study="ESTUDIO A"):
    for name in names:
        db.add(models.BotAgentInterviewer(
            agent_phone=phone, study_code=study, interviewer_name=name))
    db.commit()


def run_until_question(db):
    """Recorre hola -> estudio -> añadir -> tipo de punto y llega a la pregunta."""
    process_bot_message(PHONE, "hola", db, db)
    process_bot_message(PHONE, "1", db, db)
    process_bot_message(PHONE, "1", db, db)
    return process_bot_message(PHONE, "1", db, db)


def offered_titles(interactive):
    """Títulos visibles de la respuesta interactiva (botones o filas de lista)."""
    action = interactive.get("action", {})
    if "buttons" in action:
        return [b["reply"]["title"] for b in action["buttons"]]
    rows = action.get("sections", [{}])[0].get("rows", [])
    return [r["title"] for r in rows]


def submissions(db):
    return db.query(models.QuotaSubmission).filter(models.QuotaSubmission.is_deleted == 0).all()


def test_always_asks_even_without_roster():
    """Sin personal asignado igual pregunta, y ofrece solo al que carga."""
    db = setup_db()
    create_study(db)
    register_agent(db)

    reply, interactive = run_until_question(db)
    assert "encuestador" in reply.lower(), f"No preguntó: {reply}"
    assert submissions(db) == [], "No debe guardar antes de elegir encuestador"
    assert offered_titles(interactive) == ["Pepe"], offered_titles(interactive)

    reply, _ = process_bot_message(PHONE, "1", db, db)
    subs = submissions(db)
    assert len(subs) == 2, f"Esperaba 2 submissions, obtuve {len(subs)}"
    assert all(s.interviewer_name == "Pepe" for s in subs), [s.interviewer_name for s in subs]
    assert "Guardado con éxito" in reply, reply
    print("OK test_always_asks_even_without_roster")


def test_offers_roster_of_this_study_only():
    """Ofrece al que carga y el personal de este estudio; no el de otro estudio."""
    db = setup_db()
    create_study(db)
    register_agent(db)
    add_roster(db, ["Encuestador 1", "Encuestador 2"])
    add_roster(db, ["Encuestador 9"], study="ESTUDIO B")

    _, interactive = run_until_question(db)
    titles = offered_titles(interactive)
    assert titles == ["Pepe", "Encuestador 1", "Encuestador 2"], titles

    process_bot_message(PHONE, "2", db, db)
    subs = submissions(db)
    assert len(subs) == 2, f"Esperaba 2 submissions, obtuve {len(subs)}"
    assert all(s.interviewer_name == "Encuestador 1" for s in subs), [s.interviewer_name for s in subs]
    print("OK test_offers_roster_of_this_study_only")


def test_invalid_choice_saves_nothing():
    """Una respuesta fuera de la lista no guarda y vuelve a preguntar."""
    db = setup_db()
    create_study(db)
    register_agent(db)
    add_roster(db, ["Encuestador 1"])

    run_until_question(db)
    reply, _ = process_bot_message(PHONE, "9", db, db)
    assert submissions(db) == [], "No debe guardar con una opción inválida"
    assert "encuestador" in reply.lower(), f"No volvió a preguntar: {reply}"

    process_bot_message(PHONE, "2", db, db)
    subs = submissions(db)
    assert len(subs) == 2 and all(s.interviewer_name == "Encuestador 1" for s in subs), (
        [s.interviewer_name for s in subs]
    )
    print("OK test_invalid_choice_saves_nothing")


def test_free_text_flow_also_asks():
    """La ruta de texto libre también pregunta antes de guardar."""
    db = setup_db()
    create_study(db)
    register_agent(db)
    add_roster(db, ["Encuestador 1", "Encuestador 2"])

    process_bot_message(PHONE, "hola", db, db)
    process_bot_message(PHONE, "1", db, db)  # estudio
    reply, _ = process_bot_message(PHONE, "transporte mb hombre 18-35", db, db)
    assert "quieres agregar" in reply.lower(), reply

    reply, interactive = process_bot_message(PHONE, "1", db, db)  # confirmar
    assert "encuestador" in reply.lower(), f"No preguntó el encuestador: {reply}"
    assert submissions(db) == [], "No debe guardar antes de elegir encuestador"
    assert offered_titles(interactive) == ["Pepe", "Encuestador 1", "Encuestador 2"], offered_titles(interactive)

    process_bot_message(PHONE, "3", db, db)
    subs = submissions(db)
    assert len(subs) == 2, f"Esperaba 2 submissions, obtuve {len(subs)}"
    assert all(s.interviewer_name == "Encuestador 2" for s in subs), [s.interviewer_name for s in subs]
    print("OK test_free_text_flow_also_asks")


def test_more_than_ten_options_paginate():
    """Con más de 10 opciones aparece 'Ver más' y la segunda página se puede elegir."""
    db = setup_db()
    create_study(db)
    register_agent(db)
    add_roster(db, [f"Encuestador {i}" for i in range(1, 13)])

    reply, interactive = run_until_question(db)
    titles = offered_titles(interactive)
    assert len(titles) == 10, titles
    assert titles[-1] == "Ver más", titles
    assert interactive["type"] == "list", interactive["type"]
    assert "ver más" in reply.lower(), reply

    reply, interactive_second = process_bot_message(PHONE, "ver más", db, db)
    titles_second = offered_titles(interactive_second)
    assert titles_second == ["Encuestador 9", "Encuestador 10", "Encuestador 11", "Encuestador 12"], titles_second

    process_bot_message(PHONE, "1", db, db)
    subs = submissions(db)
    assert len(subs) == 2, f"Esperaba 2 submissions, obtuve {len(subs)}"
    assert all(s.interviewer_name == "Encuestador 9" for s in subs), [s.interviewer_name for s in subs]
    print("OK test_more_than_ten_options_paginate")


if __name__ == "__main__":
    test_always_asks_even_without_roster()
    test_offers_roster_of_this_study_only()
    test_invalid_choice_saves_nothing()
    test_free_text_flow_also_asks()
    test_more_than_ten_options_paginate()
    print("\nTodos los tests de la pregunta de encuestador pasaron")
