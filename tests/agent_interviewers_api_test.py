"""Tests de la asignacion de personal (encuestadores) por estudio en el panel.

Ejecutar con:  python tests/agent_interviewers_api_test.py

Cubre:
- GET /api/agents expone interviewers_by_study por par (supervisor, estudio).
- POST /api/agents/interviewers exige rol superuser.
- POST /api/agents/interviewers rechaza estudios que no estan permitidos.
- POST /api/agents/interviewers reemplaza la lista (no acumula) y deduplica.
- POST /api/agents/assign borra el personal de los estudios que se destildan.
- No-regresion: los campos previos de GET /api/agents siguen igual.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend import models, database, auth
from backend.main import app


class ASGIClient:
    """Cliente sincronico sobre ASGITransport (el TestClient de starlette 0.27 no
    funciona con httpx 0.28, y no queremos tocar dependencias por un test)."""

    def __init__(self, application):
        self._transport = httpx.ASGITransport(app=application)

    def request(self, method, url, **kwargs):
        async def _run():
            async with httpx.AsyncClient(
                transport=self._transport, base_url="http://testserver"
            ) as client:
                return await client.request(method, url, **kwargs)

        return asyncio.run(_run())

    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)


def build_env():
    """Arma una app con DB en memoria y un usuario autenticado controlable."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.Base.metadata.create_all(bind=engine)
    models.UsersBase.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[database.get_db] = override_db
    app.dependency_overrides[database.get_users_db] = override_db

    auth_state = {"role": "superuser"}

    def override_user():
        return models.User(
            username="admin",
            role=auth_state["role"],
            phone_number="3000000000",
        )

    app.dependency_overrides[auth.get_current_user] = override_user

    return ASGIClient(app), SessionLocal, auth_state


def seed_users(db_users, rows):
    for username, role, phone in rows:
        db_users.execute(text("""
            INSERT INTO users (username, hashed_password, role, phone_number)
            VALUES (:u, 'x', :r, :p)
        """), {"u": username, "r": role, "p": phone})
    db_users.commit()


def seed_agent(db, phone, assigned_studies):
    db.add(models.BotActiveAgent(phone_number=phone, assigned_studies=assigned_studies))
    db.commit()


def agent_payload(client, phone):
    res = client.get("/api/agents")
    assert res.status_code == 200, res.text
    for item in res.json():
        if item["phone_number"] == phone:
            return item
    raise AssertionError(f"No se encontro el agente {phone} en /api/agents")


def test_agents_endpoint_exposes_interviewers_by_study():
    """GET /api/agents debe devolver el personal agrupado por estudio."""
    client, SessionLocal, _ = build_env()
    db = SessionLocal()
    db_users = SessionLocal()

    seed_users(db_users, [
        ("pepe", "supervisor", "3111111111"),
        ("enc1", "agent", "3222222222"),
        ("enc2", "agent", "3333333333"),
    ])
    seed_agent(db, "3111111111", "1542,1543")
    db.add(models.BotAgentInterviewer(
        agent_phone="3111111111", study_code="1542", interviewer_name="Encuestador 1"))
    db.add(models.BotAgentInterviewer(
        agent_phone="3111111111", study_code="1542", interviewer_name="Encuestador 2"))
    db.commit()

    payload = agent_payload(client, "3111111111")
    assert payload["interviewers_by_study"] == {
        "1542": ["Encuestador 1", "Encuestador 2"],
        "1543": [],
    }, payload["interviewers_by_study"]

    # No-regresion: los campos que el modal ya consumia siguen presentes e iguales.
    assert payload["username"] == "pepe", payload
    assert payload["phone_number"] == "3111111111", payload
    assert payload["role"] == "supervisor", payload
    assert payload["is_active"] is True, payload
    assert payload["assigned_studies"] == "1542,1543", payload
    print("OK test_agents_endpoint_exposes_interviewers_by_study")


def test_interviewers_endpoint_requires_superuser():
    """Un usuario que no es superuser no puede cambiar el personal."""
    client, SessionLocal, auth_state = build_env()
    db = SessionLocal()
    seed_agent(db, "3111111111", "1542")

    auth_state["role"] = "supervisor"
    res = client.post("/api/agents/interviewers", json={
        "phone_number": "3111111111",
        "study_code": "1542",
        "interviewers": ["Encuestador 1"],
    })
    assert res.status_code == 403, f"Se esperaba 403 y vino {res.status_code}: {res.text}"

    stored = db.query(models.BotAgentInterviewer).all()
    assert stored == [], "No se debe guardar nada cuando falta el rol superuser"
    print("OK test_interviewers_endpoint_requires_superuser")


def test_interviewers_endpoint_rejects_study_not_allowed():
    """No se puede asignar personal a un estudio que el agente no tiene permitido."""
    client, SessionLocal, _ = build_env()
    db = SessionLocal()
    seed_agent(db, "3111111111", "1542")

    res = client.post("/api/agents/interviewers", json={
        "phone_number": "3111111111",
        "study_code": "9999",
        "interviewers": ["Encuestador 1"],
    })
    assert res.status_code == 400, f"Se esperaba 400 y vino {res.status_code}: {res.text}"
    assert db.query(models.BotAgentInterviewer).count() == 0
    print("OK test_interviewers_endpoint_rejects_study_not_allowed")


def test_interviewers_endpoint_replaces_and_dedupes():
    """Guardar de nuevo reemplaza la lista y descarta repetidos y vacios."""
    client, SessionLocal, _ = build_env()
    db = SessionLocal()
    db_users = SessionLocal()
    seed_users(db_users, [("pepe", "supervisor", "3111111111")])
    seed_agent(db, "3111111111", "1542,1543")

    res = client.post("/api/agents/interviewers", json={
        "phone_number": "3111111111",
        "study_code": "1542",
        "interviewers": ["Encuestador 1", "Encuestador 2"],
    })
    assert res.status_code == 200, res.text

    res = client.post("/api/agents/interviewers", json={
        "phone_number": "3111111111",
        "study_code": "1542",
        "interviewers": ["  Encuestador 2  ", "encuestador 2", "", "   "],
    })
    assert res.status_code == 200, res.text

    payload = agent_payload(client, "3111111111")
    assert payload["interviewers_by_study"]["1542"] == ["Encuestador 2"], payload["interviewers_by_study"]
    assert payload["interviewers_by_study"]["1543"] == [], "El otro estudio no debe tocarse"
    print("OK test_interviewers_endpoint_replaces_and_dedupes")


def test_interviewers_endpoint_requires_active_agent():
    """Si la fila no esta activa en bot_active_agents, no hay donde colgar el personal."""
    client, _, _ = build_env()
    res = client.post("/api/agents/interviewers", json={
        "phone_number": "3000000000",
        "study_code": "1542",
        "interviewers": ["Encuestador 1"],
    })
    assert res.status_code == 400, f"Se esperaba 400 y vino {res.status_code}: {res.text}"
    print("OK test_interviewers_endpoint_requires_active_agent")


def test_assign_drops_interviewers_of_removed_study():
    """Destildar un estudio debe borrar el personal de ese par y conservar el resto."""
    client, SessionLocal, _ = build_env()
    db = SessionLocal()
    db_users = SessionLocal()
    seed_users(db_users, [("pepe", "supervisor", "3111111111")])
    seed_agent(db, "3111111111", "1542,1543")
    db.add(models.BotAgentInterviewer(
        agent_phone="3111111111", study_code="1542", interviewer_name="Encuestador 1"))
    db.add(models.BotAgentInterviewer(
        agent_phone="3111111111", study_code="1543", interviewer_name="Encuestador 2"))
    db.commit()

    res = client.post("/api/agents/assign", json={
        "phone_number": "3111111111",
        "assigned_studies": "1542",
    })
    assert res.status_code == 200, res.text

    payload = agent_payload(client, "3111111111")
    assert payload["interviewers_by_study"] == {"1542": ["Encuestador 1"]}, payload["interviewers_by_study"]

    remaining = db.query(models.BotAgentInterviewer).all()
    assert [(r.study_code, r.interviewer_name) for r in remaining] == [("1542", "Encuestador 1")], (
        "El personal del estudio destildado debe borrarse: "
        f"{[(r.study_code, r.interviewer_name) for r in remaining]}"
    )
    print("OK test_assign_drops_interviewers_of_removed_study")


if __name__ == "__main__":
    test_agents_endpoint_exposes_interviewers_by_study()
    test_interviewers_endpoint_requires_superuser()
    test_interviewers_endpoint_rejects_study_not_allowed()
    test_interviewers_endpoint_replaces_and_dedupes()
    test_interviewers_endpoint_requires_active_agent()
    test_assign_drops_interviewers_of_removed_study()
    print("\nTodos los tests de personal por estudio pasaron")
