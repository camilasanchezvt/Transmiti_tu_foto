"""Piezas compartidas por las pruebas.

Las pruebas que necesitan base leen la variable DATABASE_URL_TEST. Si no está
definida se saltean, así `pytest` sigue corriendo en una máquina sin Postgres y
sólo verifica el contrato. Nunca se apunta a la base de desarrollo: el fixture
borra y recrea las tablas en cada corrida.
"""

from __future__ import annotations

import os

# Antes de importar la app: la configuración se lee una sola vez. En las pruebas
# la limpieza de Cloudinary no arranca nunca en segundo plano, aunque la máquina
# tenga ENTORNO=produccion o credenciales cargadas. Las pruebas de limpieza la
# llaman a mano, con Cloudinary simulado (test_limpieza.py).
os.environ["LIMPIEZA_ACTIVA"] = "false"

from datetime import date
from functools import lru_cache

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.database import get_db
from app.main import app
from app.models import Base, Evento, Foto, Usuario
from app.ratelimit import reiniciar as reiniciar_limite
from app.security import hashear_password

URL_PRUEBA = os.environ.get("DATABASE_URL_TEST")

sin_base = pytest.mark.skipif(
    not URL_PRUEBA, reason="definí DATABASE_URL_TEST para correr las pruebas con base"
)

EMAIL_ADMIN = "ana@transmitifoto.test"
PASSWORD_ADMIN = "fiesta1234"

EMAIL_SUPERADMIN = "sofia@transmitifoto.test"
EMAIL_ORGANIZADOR = "bruno@transmitifoto.test"
EMAIL_OTRO_ORGANIZADOR = "diego@transmitifoto.test"
EMAIL_PENDIENTE = "carla@transmitifoto.test"
EMAIL_BAJA = "ernesto@transmitifoto.test"
# Todas las cuentas de prueba que no son la de Ana usan la misma contraseña.
PASSWORD_CUENTA = "organiza1234"


@lru_cache(maxsize=None)
def hash_de(password: str) -> str:
    """bcrypt tarda un cuarto de segundo a propósito. Hashear en cada prueba
    sumaba medio minuto a la corrida; la misma contraseña da un hash que valida
    igual, así que se calcula una vez."""
    return hashear_password(password)


# El "hoy" del borrado a los 30 días en todas las pruebas. `limpieza.hoy_en_argentina`
# es el único reloj del borrado (descarga, video, pantalla, reabrir, crear), y
# los eventos del fixture `eventos` son del 12/9/2026: con el reloj de verdad,
# desde el 12/10/2026 esas pruebas darían 410 y un "2026-12-01" fijo no se
# podría crear desde el 31/12. Con el reloj fijo, la corrida no depende del día.
# Las pruebas del borrado fijan el suyo encima (monkeypatch pisa a éste).
HOY_DEL_BORRADO = date(2026, 9, 26)


@pytest.fixture(autouse=True)
def _reloj_del_borrado(monkeypatch):
    from app import limpieza

    monkeypatch.setattr(limpieza, "hoy_en_argentina", lambda: HOY_DEL_BORRADO)


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
    """Deja sólo la cuenta de Ana, admin: cada prueba empieza sin eventos ni fotos."""
    db.execute(text(
        "TRUNCATE recuperaciones_contrasena, fotos, eventos, usuarios RESTART IDENTITY CASCADE"
    ))
    db.add(
        Usuario(
            email=EMAIL_ADMIN,
            nombre="Ana Moderadora",
            password_hash=hash_de(PASSWORD_ADMIN),
            rol="admin",
            estado="activa",
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


def iniciar_sesion(cliente, email: str, password: str) -> str:
    """Un login de verdad. Devuelve el token."""
    r = cliente.post("/api/admin/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture()
def autorizado(cliente_con_base):
    """El cliente con el Bearer de Ana, que es admin, sacado de un login de verdad."""
    token = iniciar_sesion(cliente_con_base, EMAIL_ADMIN, PASSWORD_ADMIN)
    cliente_con_base.headers.update({"Authorization": f"Bearer {token}"})
    return cliente_con_base


# ─────────────────────────────────────────────────────────────
# Cuentas: una superadmin, organizadores, una pendiente y una dada de baja
# ─────────────────────────────────────────────────────────────

def nueva_cuenta(db, email: str, nombre: str, rol: str = "organizador",
                 estado: str = "activa", password: str = PASSWORD_CUENTA) -> Usuario:
    cuenta = Usuario(email=email, nombre=nombre, password_hash=hash_de(password),
                     rol=rol, estado=estado)
    db.add(cuenta)
    db.commit()
    return cuenta


@pytest.fixture()
def organizador(limpiar) -> Usuario:
    return nueva_cuenta(limpiar, EMAIL_ORGANIZADOR, "Bruno Organizador")


@pytest.fixture()
def otro_organizador(limpiar) -> Usuario:
    return nueva_cuenta(limpiar, EMAIL_OTRO_ORGANIZADOR, "Diego Otro")


@pytest.fixture()
def cuenta_pendiente(limpiar) -> Usuario:
    return nueva_cuenta(limpiar, EMAIL_PENDIENTE, "Carla Pendiente", estado="pendiente")


@pytest.fixture()
def cuenta_baja(limpiar) -> Usuario:
    return nueva_cuenta(limpiar, EMAIL_BAJA, "Ernesto de Baja", estado="baja")


@pytest.fixture()
def superadmin(limpiar) -> Usuario:
    return nueva_cuenta(limpiar, EMAIL_SUPERADMIN, "Sofía Superadmin", rol="superadmin")


@pytest.fixture()
def autorizado_superadmin(cliente_con_base, superadmin):
    """Un cliente APARTE con el Bearer de Sofía, superadmin. Igual que el de
    Bruno: otro TestClient, así convive con `autorizado` en la misma prueba."""
    with TestClient(app) as c:
        token = iniciar_sesion(c, EMAIL_SUPERADMIN, PASSWORD_CUENTA)
        c.headers.update({"Authorization": f"Bearer {token}"})
        yield c


@pytest.fixture()
def autorizado_organizador(cliente_con_base, organizador):
    """Un cliente APARTE con el Bearer de Bruno, organizador.

    Es otro TestClient y no el mismo con otro header: así una prueba puede usar
    a la vez el de Ana (`autorizado`) y el de Bruno sin que uno pise al otro.
    Comparte la base porque el reemplazo de get_db es de la app, no del cliente.
    """
    with TestClient(app) as c:
        token = iniciar_sesion(c, EMAIL_ORGANIZADOR, PASSWORD_CUENTA)
        c.headers.update({"Authorization": f"Bearer {token}"})
        yield c


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

# Imágenes que existen de verdad en la nube pública `demo` de Cloudinary. Se
# usan chicas a propósito: la prueba del ZIP las descarga de verdad.
IMAGENES_REALES = [
    "couple", "sample", "balloons", "woman", "cld-sample", "flower",
    "bike", "lady", "horses", "cld-sample-2", "coffee_cup", "yellow_tulip",
]


def url_de(public_id: str) -> str:
    """URL con la forma que valida el backend. NO resuelve: sirve para probar la
    validación, no para descargar."""
    return f"{URL_BASE}/v1700000000/{public_id}.jpg"


def url_real(indice: int) -> str:
    """URL que sí devuelve una imagen. La usa el fixture para que la prueba del
    ZIP baje bytes de verdad."""
    return f"{URL_BASE}/c_fill,w_400,h_300/{IMAGENES_REALES[indice % len(IMAGENES_REALES)]}.jpg"


@pytest.fixture()
def eventos(limpiar):
    """Tres eventos de Ana —activo, cerrado y borrador— y las fotos del activo.

    El activo lleva 6 aprobadas, 2 pendientes y 1 rechazada. El cerrado lleva 2
    aprobadas, para poder comprobar que su pantalla sigue andando y que ninguna
    de esas fotos se filtra a la pantalla del otro.

    Para un organizador, los tres son eventos ajenos.
    """
    db = limpiar
    admin = db.scalar(select(Usuario).where(Usuario.email == EMAIL_ADMIN))

    def nuevo(nombre, codigo, token, estado, **extra):
        e = Evento(
            usuario_id=admin.id,
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
        db.add(Foto(evento_id=activo.id, public_id=pid, url=url_real(i), ancho=1600,
                    alto=1200, bytes=100000 + i, estado=estado,
                    dispositivo_hash="d" * 32, nombre_invitado=f"Invitado {i}"))
    for i in range(2):
        pid = f"eventos/{CODIGO_CERRADO}/c{i:02d}"
        db.add(Foto(evento_id=cerrado.id, public_id=pid, url=url_real(i + 6), ancho=1200,
                    alto=1600, bytes=90000 + i, estado="aprobada",
                    dispositivo_hash="e" * 32, nombre_invitado="Malena"))
    db.commit()

    return {"activo": activo, "cerrado": cerrado, "borrador": borrador}
