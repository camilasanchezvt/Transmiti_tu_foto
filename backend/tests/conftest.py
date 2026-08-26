"""Piezas compartidas por las pruebas.

Las pruebas que necesitan base leen la variable DATABASE_URL_TEST. Si no está
definida se saltean, así `pytest` sigue corriendo en una máquina sin Postgres y
sólo verifica el contrato. Nunca se apunta a la base de desarrollo: el fixture
borra y recrea las tablas en cada corrida.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.database import get_db
from app.main import app
from app.models import Administrador, Base
from app.security import hashear_password

URL_PRUEBA = os.environ.get("DATABASE_URL_TEST")

sin_base = pytest.mark.skipif(
    not URL_PRUEBA, reason="definí DATABASE_URL_TEST para correr las pruebas con base"
)

EMAIL_ADMIN = "ana@transmitifoto.test"
PASSWORD_ADMIN = "fiesta1234"


@pytest.fixture(scope="session")
def motor_prueba():
    if not URL_PRUEBA:
        pytest.skip("sin DATABASE_URL_TEST")
    motor = create_engine(URL_PRUEBA, pool_pre_ping=True)
    with motor.connect() as c:
        # Arrancar siempre de cero: una prueba que depende de restos de la
        # corrida anterior pasa hoy y falla mañana sin que nadie toque nada.
        c.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        c.execute(text("CREATE SCHEMA public"))
        c.commit()
    Base.metadata.create_all(motor)
    yield motor
    motor.dispose()


@pytest.fixture()
def db(motor_prueba):
    Sesion = sessionmaker(bind=motor_prueba, autoflush=False, expire_on_commit=False)
    sesion = Sesion()
    try:
        yield sesion
    finally:
        sesion.rollback()
        sesion.close()


@pytest.fixture()
def limpiar(db):
    """Deja sólo el administrador: cada prueba empieza sin eventos ni fotos."""
    db.execute(text("TRUNCATE fotos, eventos, administradores RESTART IDENTITY CASCADE"))
    db.add(
        Administrador(
            email=EMAIL_ADMIN,
            nombre="Ana Moderadora",
            password_hash=hashear_password(PASSWORD_ADMIN),
        )
    )
    db.commit()
    return db


@pytest.fixture()
def cliente_con_base(motor_prueba, limpiar):
    """Cliente cuyo get_db apunta a la base de pruebas."""
    Sesion = sessionmaker(bind=motor_prueba, autoflush=False, expire_on_commit=False)

    def get_db_prueba():
        sesion = Sesion()
        try:
            yield sesion
        finally:
            sesion.close()

    app.dependency_overrides[get_db] = get_db_prueba
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def autorizado(cliente_con_base):
    """El cliente con un Bearer real, sacado de un login de verdad."""
    r = cliente_con_base.post(
        "/api/admin/login", json={"email": EMAIL_ADMIN, "password": PASSWORD_ADMIN}
    )
    assert r.status_code == 200, r.text
    cliente_con_base.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
    return cliente_con_base
