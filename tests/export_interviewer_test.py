"""Tests de la descarga CSV/Excel: el archivo debe mostrar encuestador y supervisor.

Ejecutar con:  python tests/export_interviewer_test.py

Cubre:
- La columna "Encuestador" sigue en la misma posicion y trae el nombre del encuestador.
- La descarga agrega "Supervisor" resuelto desde users, tolerando el prefijo 57.
- Si el telefono no esta en users, el supervisor cae al telefono crudo.
- No-regresion: las 7 primeras columnas no se mueven.
"""
import asyncio
import csv
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend import models, database
from backend.main import app


class ASGIClient:
    def __init__(self, application):
        self._transport = httpx.ASGITransport(app=application)

    def get(self, url, **kwargs):
        async def _run():
            async with httpx.AsyncClient(
                transport=self._transport, base_url="http://testserver"
            ) as client:
                return await client.request("GET", url, **kwargs)

        return asyncio.run(_run())


def build_env():
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
    return ASGIClient(app), SessionLocal


def seed_study_with_submissions(db):
    quota = models.BotQuota(
        study_code="1542",
        category="Hombre | 18-35",
        value="MB",
        target_count=10,
        current_count=3,
        point_type="Parque",
    )
    db.add(quota)
    db.commit()
    db.refresh(quota)

    db.add(models.QuotaSubmission(
        bot_quota_id=quota.id, phone_number="3111111111", interviewer_name="Encuestador 1"))
    db.add(models.QuotaSubmission(
        bot_quota_id=quota.id, phone_number="573111111111", interviewer_name="Encuestador 2"))
    db.add(models.QuotaSubmission(
        bot_quota_id=quota.id, phone_number="3009999999", interviewer_name="Encuestador 3"))
    db.commit()


def seed_supervisor(db_users):
    db_users.execute(text("""
        INSERT INTO users (username, hashed_password, role, phone_number)
        VALUES ('pepe', 'x', 'supervisor', '3111111111')
    """))
    db_users.commit()


def read_csv_response(response):
    assert response.status_code == 200, response.text
    body = response.content.decode("utf-8-sig")
    return list(csv.reader(io.StringIO(body)))


def test_export_shows_interviewer_and_supervisor():
    client, SessionLocal = build_env()
    db = SessionLocal()
    db_users = SessionLocal()
    seed_supervisor(db_users)
    seed_study_with_submissions(db)

    rows = read_csv_response(client.get("/api/export-data/1542"))
    header, data = rows[0], rows[1:]

    assert header[:8] == [
        "ID", "Fecha", "Estudio", "Tipo de Punto", "Categoría", "Valor",
        "Número Celular", "Encuestador",
    ], f"Las columnas previas no deben moverse: {header}"
    assert header[8] == "Supervisor", f"Falta la columna Supervisor: {header}"

    by_phone = {row[6]: row for row in data}
    assert by_phone["3111111111"][7] == "Encuestador 1", by_phone["3111111111"]
    assert by_phone["3111111111"][8] == "pepe", by_phone["3111111111"]

    # El webhook guarda el telefono en formato Meta (con 57): debe resolver igual.
    assert by_phone["573111111111"][8] == "pepe", by_phone["573111111111"]

    # Si el telefono no esta en users, se muestra tal cual en vez de vaciarse.
    assert by_phone["3009999999"][8] == "3009999999", by_phone["3009999999"]
    print("OK test_export_shows_interviewer_and_supervisor")


if __name__ == "__main__":
    test_export_shows_interviewer_and_supervisor()
    print("\nTodos los tests de exportacion pasaron")
