"""Piezas compartidas por las pruebas.

Las pruebas que necesitan base leen la variable DATABASE_URL_TEST. Si no está
definida se saltean, así `pytest` sigue corriendo en una máquina sin Postgres y
sólo verifica el contrato. Nunca se apunta a la base de desarrollo: el fixture
borra y recrea las tablas en cada corrida.
"""

from __future__ import annotations

import os
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.database import get_db
from app.main import app
from app.models import Administrador, Base, Evento, Foto
from app.ratelimit import reiniciar as reiniciar_limite
from app.security import hashear_password

URL_PRUEBA = os.environ.get("DATABASE_URL_TEST")

sin_base = pytest.mark.skipif(
    not URL_PRUEBA, reason="definí DATABASE_URL_TEST para correr las pruebas con base"
)

EMAIL_ADMIN = "ana@transmitifoto.test"
PASSWORD_ADMIN = "fiesta1234"


@pytest.fixture(autouse=True)
def _limite_limpio():
    """El límite de pedidos vive en memoria del proceso: si no se reinicia, una
    prueba que gasta la cuota hace fallar a la siguiente."""
    reiniciar_limite()
    yield
    reiniciar_limite()


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


# ─────────────────────────────────────────────────────────────
# Eventos de prueba, con los mismos códigos y tokens del seed
# ─────────────────────────────────────────────────────────────

CODIGO_ACTIVO = "ab12cd34"
CODIGO_CERRADO = "ef56gh78"
CODIGO_BORRADOR = "dr00af00"
TOKEN_ACTIVO = "64syPN4YFgbJibLfIOlrjI51R0HFlKDm"
TOKEN_CERRADO = "8MX4OqECds7IhkCmlK7vub76PntouGz1"
TOKEN_BORRADOR = "B" * 32

URL_BASE = "https://res.cloudinary.com/demo/image/upload"


def url_de(public_id: str) -> str:
    return f"{URL_BASE}/v1700000000/{public_id}.jpg"


@pytest.fixture()
def eventos(limpiar):
    """Tres eventos —activo, cerrado y borrador— y las fotos del activo.

    El activo lleva 6 aprobadas, 2 pendientes y 1 rechazada. El cerrado lleva 2
    aprobadas, para poder comprobar que su pantalla sigue andando y que ninguna
    de esas fotos se filtra a la pantalla del otro.
    """
    db = limpiar
    admin = db.scalar(select(Administrador).where(Administrador.email == EMAIL_ADMIN))

    def nuevo(nombre, codigo, token, estado, **extra):
        e = Evento(
            admin_id=admin.id,
            nombre=nombre,
            fecha_evento=date(2026, 9, 12),
            codigo_publico=codigo,
            token_pantalla=token,
            estado=estado,
            **extra,
        )
        db.add(e)
        return e

    activo = nuevo("Casamiento Ana y Juan", CODIGO_ACTIVO, TOKEN_ACTIVO, "activo",
                   max_fotos_por_dispositivo=10, segundos_por_foto=7)
    cerrado = nuevo("Cumple de 15 de Malena", CODIGO_CERRADO, TOKEN_CERRADO, "cerrado",
                    segundos_por_foto=6)
    borrador = nuevo("Sin publicar", CODIGO_BORRADOR, TOKEN_BORRADOR, "borrador")
    db.commit()

    plan = ["aprobada"] * 6 + ["pendiente"] * 2 + ["rechazada"]
    for i, estado in enumerate(plan):
        pid = f"eventos/{CODIGO_ACTIVO}/f{i:02d}"
        db.add(Foto(evento_id=activo.id, public_id=pid, url=url_de(pid), ancho=1600,
                    alto=1200, bytes=100000 + i, estado=estado,
                    dispositivo_hash="d" * 32, nombre_invitado=f"Invitado {i}"))
    for i in range(2):
        pid = f"eventos/{CODIGO_CERRADO}/c{i:02d}"
        db.add(Foto(evento_id=cerrado.id, public_id=pid, url=url_de(pid), ancho=1200,
                    alto=1600, bytes=90000 + i, estado="aprobada",
                    dispositivo_hash="e" * 32, nombre_invitado="Malena"))
    db.commit()

    return {"activo": activo, "cerrado": cerrado, "borrador": borrador}
