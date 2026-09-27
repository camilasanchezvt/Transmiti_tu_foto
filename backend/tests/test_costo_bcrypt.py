"""bcrypt con 10 rondas, y los hashes de 12 que se actualizan solos al entrar.

27-sep-2026: el login tardaba 1,9 a 3,7 s en Render gratuito, casi todo bcrypt
con 12 rondas (el costo por defecto de passlib). Se bajó a 10, en un solo lugar:
`security.RONDAS_BCRYPT`. Lo que se prueba acá, en el orden del archivo:

- Todo hash nuevo sale con 10 rondas: el de `hashear_password`, el de relleno
  del login (si costara otra cosa que uno real, el tiempo delataría qué emails
  tienen cuenta), el del registro, el de restablecer y el de cambiar la
  contraseña.
- Una cuenta con hash de 12 entra y queda con uno de 10; una con 10 no se
  reescribe. Con la contraseña incorrecta, o si la cuenta no entra (pendiente
  o de baja), no se escribe nada.
- Los locks del login: con un hash al día sigue siendo FOR SHARE (dos logins
  no se frenan); con uno viejo es FOR NO KEY UPDATE desde antes de bcrypt, y
  dos logins a la vez de esa cuenta van de a uno, sin trabarse. Un
  restablecimiento que llega en el medio sigue cortando la sesión emitida.

Las que necesitan Postgres llevan @sin_base y se saltean sin DATABASE_URL_TEST.
"""

from __future__ import annotations

import logging
import statistics
import threading
import time
from datetime import datetime, timedelta, timezone
from functools import lru_cache

import bcrypt
import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from app import ratelimit
from app.models import RecuperacionContrasena, Usuario
from app.routers import admin as rutas_admin
from app.security import (
    RONDAS_BCRYPT,
    crear_token,
    hash_de_token,
    hash_desactualizado,
    hashear_password,
    verificar_password,
    verificar_y_actualizar,
)
from tests.conftest import (
    EMAIL_BAJA,
    EMAIL_ORGANIZADOR,
    EMAIL_PENDIENTE,
    PASSWORD_CUENTA,
    nueva_cuenta,
    sin_base,
)

CLAVE = "clave-de-antes-larga"
OTRA = "otra-clave-bien-larga"


def rondas(password_hash: str) -> int:
    """El costo que dice el propio hash: `$2b$10$…` → 10."""
    return int(password_hash.split("$")[2])


@lru_cache(maxsize=None)
def hash_de_12(password: str) -> str:
    """Un hash como los que quedaron en la base antes del cambio. Con bcrypt
    directo, sin passlib: así no depende de la configuración que se prueba."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12, prefix=b"2b")).decode()


def login(cliente, email: str, password: str):
    return cliente.post("/api/admin/login", json={"email": email, "password": password})


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def hash_guardado(db, usuario_id: int) -> str:
    db.expire_all()
    return db.scalar(select(Usuario.password_hash).where(Usuario.id == usuario_id))


def cuenta_con_hash_de_12(db, email: str = EMAIL_ORGANIZADOR, estado: str = "activa") -> Usuario:
    cuenta = Usuario(email=email, nombre="Cuenta de antes", password_hash=hash_de_12(CLAVE),
                     rol="organizador", estado=estado)
    db.add(cuenta)
    db.commit()
    return cuenta


# ─────────────────────────────────────────────────────────────
# Sin base: el costo y las funciones de security.py
# ─────────────────────────────────────────────────────────────

def test_el_costo_es_10():
    assert RONDAS_BCRYPT == 10
    assert rondas(hashear_password(CLAVE)) == 10


def test_el_hash_de_relleno_cuesta_lo_mismo_que_uno_real():
    """El login compara contra este hash cuando el email no existe. Si tuviera
    otro costo que los reales, responder más rápido o más lento delataría qué
    emails tienen cuenta."""
    relleno = rutas_admin._hash_de_relleno()
    assert rondas(relleno) == rondas(hashear_password(CLAVE)) == RONDAS_BCRYPT
    assert not hash_desactualizado(relleno)


def test_un_hash_de_12_esta_desactualizado_y_uno_de_10_no():
    assert hash_desactualizado(hash_de_12(CLAVE))
    assert not hash_desactualizado(hashear_password(CLAVE))


@pytest.mark.parametrize("raro", ["", "no-es-un-hash", "$2b$10$corto"])
def test_un_hash_que_no_se_reconoce_no_rompe_nada(raro):
    assert hash_desactualizado(raro) is False
    assert verificar_y_actualizar(CLAVE, raro) == (False, None)
    assert verificar_password(CLAVE, raro) is False


def test_los_hashes_de_12_siguen_validando():
    """Nadie queda afuera por el cambio: la contraseña de siempre entra."""
    assert verificar_password(CLAVE, hash_de_12(CLAVE))
    assert not verificar_password(OTRA, hash_de_12(CLAVE))


def test_verificar_y_actualizar():
    viejo = hash_de_12(CLAVE)

    # Sin la contraseña correcta no hay hash nuevo, nunca.
    assert verificar_y_actualizar(OTRA, viejo) == (False, None)

    valida, nuevo = verificar_y_actualizar(CLAVE, viejo)
    assert valida and nuevo is not None
    assert rondas(nuevo) == 10 and nuevo != viejo
    assert verificar_password(CLAVE, nuevo) and not verificar_password(OTRA, nuevo)

    # Con un hash al día no hay nada que guardar.
    assert verificar_y_actualizar(CLAVE, nuevo) == (True, None)
    assert verificar_y_actualizar(OTRA, nuevo) == (False, None)


def test_el_aviso_de_passlib_no_ensucia_el_log():
    """passlib 1.7.4 deja un traceback al leer la versión de bcrypt 4. Es
    inofensivo, pero en el log de Render parece que el login falló."""
    assert logging.getLogger("passlib.handlers.bcrypt").getEffectiveLevel() >= logging.ERROR


# ─────────────────────────────────────────────────────────────
# Con base: el login actualiza el hash, y nada más
# ─────────────────────────────────────────────────────────────

@sin_base
def test_una_cuenta_con_hash_de_12_entra_y_queda_con_10(cliente_con_base, db):
    cuenta = cuenta_con_hash_de_12(db)
    viejo = hash_guardado(db, cuenta.id)

    r = login(cliente_con_base, EMAIL_ORGANIZADOR, CLAVE)
    assert r.status_code == 200, r.text
    assert set(r.json()) == {"token", "expira_en"}
    assert cliente_con_base.get("/api/admin/yo", headers=bearer(r.json()["token"])).status_code == 200

    nuevo = hash_guardado(db, cuenta.id)
    assert nuevo != viejo and rondas(nuevo) == 10
    assert verificar_password(CLAVE, nuevo) and not verificar_password(OTRA, nuevo)

    # La segunda vez ya está al día: entra y no se reescribe.
    assert login(cliente_con_base, EMAIL_ORGANIZADOR, CLAVE).status_code == 200
    assert hash_guardado(db, cuenta.id) == nuevo


@sin_base
def test_una_cuenta_con_hash_de_10_no_se_reescribe(cliente_con_base, organizador, db):
    antes = hash_guardado(db, organizador.id)
    assert rondas(antes) == 10
    for _ in range(2):
        assert login(cliente_con_base, EMAIL_ORGANIZADOR, PASSWORD_CUENTA).status_code == 200
    assert hash_guardado(db, organizador.id) == antes


@sin_base
def test_con_la_contrasena_incorrecta_no_se_escribe_nada(cliente_con_base, db):
    cuenta = cuenta_con_hash_de_12(db)
    viejo = hash_guardado(db, cuenta.id)
    r = login(cliente_con_base, EMAIL_ORGANIZADOR, OTRA)
    assert r.status_code == 401, r.text
    assert r.json()["error"]["codigo"] == "NO_AUTORIZADO"
    assert hash_guardado(db, cuenta.id) == viejo


@sin_base
@pytest.mark.parametrize("email, estado, http", [
    (EMAIL_PENDIENTE, "pendiente", 401),
    (EMAIL_BAJA, "baja", 403),
])
def test_una_cuenta_que_no_entra_no_se_actualiza(cliente_con_base, db, email, estado, http):
    """Sólo se reescribe el hash cuando la cuenta entra. Una pendiente o de baja
    responde lo mismo que antes y su hash queda como estaba."""
    cuenta = cuenta_con_hash_de_12(db, email=email, estado=estado)
    viejo = hash_guardado(db, cuenta.id)
    r = login(cliente_con_base, email, CLAVE)
    assert r.status_code == http, r.text
    assert r.json()["error"]["codigo"] == "NO_AUTORIZADO"
    assert hash_guardado(db, cuenta.id) == viejo


@sin_base
def test_el_log_avisa_la_actualizacion_sin_el_email(cliente_con_base, db, caplog):
    cuenta = cuenta_con_hash_de_12(db)
    with caplog.at_level(logging.INFO, logger=rutas_admin.log_cuentas.name):
        assert login(cliente_con_base, EMAIL_ORGANIZADOR, CLAVE).status_code == 200
        assert login(cliente_con_base, EMAIL_ORGANIZADOR, CLAVE).status_code == 200
    avisos = [x.getMessage() for x in caplog.records if x.name == rutas_admin.log_cuentas.name]
    assert avisos == [f"cuentas: la cuenta {cuenta.id} entró y su contraseña pasó a 10 rondas de bcrypt"]
    assert EMAIL_ORGANIZADOR not in caplog.text and CLAVE not in caplog.text


@sin_base
def test_un_email_inexistente_tarda_lo_mismo_que_uno_que_existe(cliente_con_base, organizador):
    """Con el relleno de 10 y los hashes de 10, un email que no existe y una
    contraseña incorrecta tardan lo mismo. Si el relleno fuera de 12, el que no
    existe tardaría cuatro veces más. Margen amplio, para no depender de la
    máquina: la mitad o el doble."""
    rutas_admin._hash_de_relleno()  # que la primera vez no cuente el cálculo
    existe, no_existe = [], []
    for i in range(5):
        ratelimit.reiniciar()
        inicio = time.perf_counter()
        assert login(cliente_con_base, EMAIL_ORGANIZADOR, OTRA).status_code == 401
        existe.append(time.perf_counter() - inicio)
        inicio = time.perf_counter()
        assert login(cliente_con_base, f"nadie{i}@transmitifoto.test", OTRA).status_code == 401
        no_existe.append(time.perf_counter() - inicio)
    proporcion = statistics.median(no_existe) / statistics.median(existe)
    assert 0.5 < proporcion < 2, (existe, no_existe)


# ─────────────────────────────────────────────────────────────
# Con base: registro, restablecer y cambiar la contraseña
# ─────────────────────────────────────────────────────────────

@sin_base
def test_el_registro_guarda_un_hash_de_10(cliente_con_base, db):
    r = cliente_con_base.post("/api/cuentas/registro", json={
        "email": "nueva@transmitifoto.test", "nombre": "Nueva", "password": CLAVE,
    })
    assert r.status_code == 201, r.text
    db.expire_all()
    guardado = db.scalar(select(Usuario.password_hash)
                         .where(Usuario.email == "nueva@transmitifoto.test"))
    assert rondas(guardado) == 10 and verificar_password(CLAVE, guardado)


@sin_base
def test_restablecer_guarda_un_hash_de_10(cliente_con_base, db):
    cuenta = cuenta_con_hash_de_12(db)
    ahora = datetime.now(timezone.utc)
    token = "t" * 43
    db.add(RecuperacionContrasena(usuario_id=cuenta.id, token_hash=hash_de_token(token),
                                  creado_en=ahora, vence_en=ahora + timedelta(hours=1)))
    db.commit()
    r = cliente_con_base.post("/api/cuentas/restablecer", json={"token": token, "password": OTRA})
    assert r.status_code == 200, r.text
    guardado = hash_guardado(db, cuenta.id)
    assert rondas(guardado) == 10 and verificar_password(OTRA, guardado)


@sin_base
def test_cambiar_la_contrasena_guarda_un_hash_de_10(cliente_con_base, db):
    """Con un token firmado a mano, sin pasar por el login (que ya la habría
    actualizado): la cuenta llega con el hash de 12 al cambio."""
    cuenta = cuenta_con_hash_de_12(db)
    token, _ = crear_token(cuenta.id, cuenta.email)
    r = cliente_con_base.post("/api/admin/yo/contrasena", headers=bearer(token),
                              json={"actual": CLAVE, "nueva": OTRA})
    assert r.status_code == 200, r.text
    guardado = hash_guardado(db, cuenta.id)
    assert rondas(guardado) == 10 and verificar_password(OTRA, guardado)


# ─────────────────────────────────────────────────────────────
# Con base: los locks del login
# ─────────────────────────────────────────────────────────────

class BcryptQueSeTraba:
    """`verificar_y_actualizar` de verdad, pero el PRIMER login se queda
    esperando hasta `soltar`, con la fila de la cuenta tomada. `adentro` avisa
    que ya llegó. Anota qué devolvió cada llamada."""

    def __init__(self) -> None:
        self.adentro = threading.Event()
        self.soltar = threading.Event()
        self.resultados: list[tuple[bool, str | None]] = []
        self._candado = threading.Lock()

    def __call__(self, password: str, password_hash: str):
        with self._candado:
            primero = not self.adentro.is_set()
            self.adentro.set()
        if primero:
            assert self.soltar.wait(15), "nadie soltó el login"
        resultado = verificar_y_actualizar(password, password_hash)
        self.resultados.append(resultado)
        return resultado


@pytest.fixture()
def bcrypt_trabado(monkeypatch):
    trabado = BcryptQueSeTraba()
    monkeypatch.setattr(rutas_admin, "verificar_y_actualizar", trabado)
    yield trabado
    trabado.soltar.set()


@pytest.fixture()
def fabrica(motor_prueba):
    return sessionmaker(bind=motor_prueba, autoflush=False, expire_on_commit=False)


def en_un_hilo(resultados: dict, clave: str, funcion) -> threading.Thread:
    def correr():
        try:
            resultados[clave] = funcion()
        except Exception as e:  # noqa: BLE001 — la prueba lo mira después
            resultados[clave] = e
    hilo = threading.Thread(target=correr, daemon=True)
    hilo.start()
    return hilo


def se_puede_tomar(fabrica, usuario_id: int, modo: str) -> bool:
    """¿Otra conexión puede tomar la fila de la cuenta en `modo` sin esperar?"""
    with fabrica() as otra:
        try:
            otra.execute(text(f"SELECT id FROM usuarios WHERE id = :id {modo} NOWAIT"),
                         {"id": usuario_id})
            return True
        except OperationalError:
            return False
        finally:
            otra.rollback()


def esperar_a_que_alguien_espere_un_lock(motor, segundos: float = 10) -> None:
    """Cada vuelta en su propia transacción: pg_stat_activity se lee una vez por
    transacción y después queda fija."""
    limite = time.monotonic() + segundos
    with motor.connect() as conexion:
        while time.monotonic() < limite:
            esperando = conexion.execute(text(
                "SELECT count(*) FROM pg_stat_activity "
                "WHERE datname = current_database() AND wait_event_type = 'Lock'"
            )).scalar()
            conexion.rollback()
            if esperando:
                return
            time.sleep(0.05)
    raise AssertionError("nadie quedó esperando el lock de la cuenta")


@sin_base
def test_con_el_hash_al_dia_el_login_sigue_con_for_share(cliente_con_base, organizador,
                                                         fabrica, bcrypt_trabado):
    """Mientras corre bcrypt, otro login (FOR SHARE) no espera; un cambio de
    contraseña (FOR NO KEY UPDATE) sí."""
    resultados: dict = {}
    hilo = en_un_hilo(resultados, "login",
                      lambda: login(cliente_con_base, EMAIL_ORGANIZADOR, PASSWORD_CUENTA))
    try:
        assert bcrypt_trabado.adentro.wait(15)
        assert se_puede_tomar(fabrica, organizador.id, "FOR SHARE")
        assert not se_puede_tomar(fabrica, organizador.id, "FOR NO KEY UPDATE")
    finally:
        bcrypt_trabado.soltar.set()
        hilo.join(15)
    assert resultados["login"].status_code == 200, resultados["login"].text
    assert bcrypt_trabado.resultados == [(True, None)]


@sin_base
def test_con_un_hash_viejo_el_login_toma_la_fila_antes_de_bcrypt(cliente_con_base, db,
                                                                 fabrica, bcrypt_trabado):
    """Para poder escribir el hash nuevo sin trabarse con otro login, la fila se
    toma con FOR NO KEY UPDATE ANTES de bcrypt. Las claves foráneas de fotos y
    eventos (FOR KEY SHARE) siguen sin esperar."""
    cuenta = cuenta_con_hash_de_12(db)
    resultados: dict = {}
    hilo = en_un_hilo(resultados, "login", lambda: login(cliente_con_base, EMAIL_ORGANIZADOR, CLAVE))
    try:
        assert bcrypt_trabado.adentro.wait(15)
        assert not se_puede_tomar(fabrica, cuenta.id, "FOR SHARE")
        assert se_puede_tomar(fabrica, cuenta.id, "FOR KEY SHARE")
    finally:
        bcrypt_trabado.soltar.set()
        hilo.join(15)
    assert resultados["login"].status_code == 200, resultados["login"].text
    assert rondas(hash_guardado(db, cuenta.id)) == 10


@sin_base
def test_dos_logins_a_la_vez_con_un_hash_viejo_no_se_traban(cliente_con_base, db,
                                                            motor_prueba, bcrypt_trabado):
    """Con los dos en FOR SHARE, los dos querían escribir y cada uno esperaba al
    otro: Postgres cortaba uno con un error de deadlock (un 500). Ahora el
    segundo espera al primero, encuentra el hash ya actualizado y no escribe."""
    cuenta = cuenta_con_hash_de_12(db)
    resultados: dict = {}
    primero = en_un_hilo(resultados, "primero",
                         lambda: login(cliente_con_base, EMAIL_ORGANIZADOR, CLAVE))
    segundo = None
    try:
        assert bcrypt_trabado.adentro.wait(15)
        segundo = en_un_hilo(resultados, "segundo",
                             lambda: login(cliente_con_base, EMAIL_ORGANIZADOR, CLAVE))
        esperar_a_que_alguien_espere_un_lock(motor_prueba)
    finally:
        bcrypt_trabado.soltar.set()
        primero.join(15)
        if segundo is not None:
            segundo.join(15)

    for clave in ("primero", "segundo"):
        assert resultados[clave].status_code == 200, resultados[clave].text
    [(valida_1, nuevo_1), (valida_2, nuevo_2)] = bcrypt_trabado.resultados
    assert valida_1 and nuevo_1 is not None
    assert valida_2 and nuevo_2 is None, "el segundo tenía que encontrar el hash nuevo"
    assert hash_guardado(db, cuenta.id) == nuevo_1


@sin_base
def test_restablecer_mientras_entra_con_un_hash_viejo_corta_esa_sesion(
    cliente_con_base, db, motor_prueba, bcrypt_trabado,
):
    """El hash nuevo se guarda después de emitir el token y antes de soltar la
    fila: un restablecimiento que llega en el medio espera, y su
    `sesiones_desde` queda después del `iat` del token, que muere."""
    cuenta = cuenta_con_hash_de_12(db)
    ahora = datetime.now(timezone.utc)
    token_link = "r" * 43
    db.add(RecuperacionContrasena(usuario_id=cuenta.id, token_hash=hash_de_token(token_link),
                                  creado_en=ahora, vence_en=ahora + timedelta(hours=1)))
    db.commit()

    resultados: dict = {}
    entra = en_un_hilo(resultados, "login",
                       lambda: login(cliente_con_base, EMAIL_ORGANIZADOR, CLAVE))
    restablece = None
    try:
        assert bcrypt_trabado.adentro.wait(15)
        restablece = en_un_hilo(resultados, "restablecer", lambda: cliente_con_base.post(
            "/api/cuentas/restablecer", json={"token": token_link, "password": OTRA}))
        esperar_a_que_alguien_espere_un_lock(motor_prueba)
    finally:
        bcrypt_trabado.soltar.set()
        entra.join(15)
        if restablece is not None:
            restablece.join(15)

    assert resultados["login"].status_code == 200, resultados["login"].text
    assert resultados["restablecer"].status_code == 200, resultados["restablecer"].text
    sesion = resultados["login"].json()["token"]
    r = cliente_con_base.get("/api/admin/yo", headers=bearer(sesion))
    assert r.status_code == 401, "la sesión de la contraseña vieja tenía que morir"

    guardado = hash_guardado(db, cuenta.id)
    assert rondas(guardado) == 10 and verificar_password(OTRA, guardado)
    assert login(cliente_con_base, EMAIL_ORGANIZADOR, CLAVE).status_code == 401
    assert login(cliente_con_base, EMAIL_ORGANIZADOR, OTRA).status_code == 200


@sin_base
def test_una_cuenta_nueva_del_fixture_ya_es_de_10(limpiar):
    """Las cuentas de las pruebas (conftest.hash_de) salen de hashear_password:
    el resto de la suite prueba el camino de todos los días, sin rehash."""
    cuenta = nueva_cuenta(limpiar, "otra@transmitifoto.test", "Otra")
    assert rondas(cuenta.password_hash) == 10
