"""Olvidé mi contraseña: POST /api/cuentas/recuperar y /restablecer, y las
sesiones que se cierran (`usuarios.sesiones_desde`).

Las reglas, en el orden del archivo:

- `recuperar` responde SIEMPRE lo mismo, exista o no la cuenta, y sin una
  diferencia de tiempo que la delate: el email sale después de la respuesta.
  Sólo una cuenta `activa` recibe el email; pendiente o de baja, no.
- El link lleva el token en el fragmento (`#token=`), sirve una vez y vence
  en una hora. Un pedido nuevo anula los anteriores. En la base queda sólo el
  hash del token.
- `restablecer` con un token inventado, vacío, vencido, usado, anulado o de una
  cuenta que ya no está activa responde siempre el mismo error. Con uno que
  sirve, cambia la contraseña y cierra TODAS las sesiones de la cuenta.
- Topes: 5 por hora por IP y 3 por hora por email en `recuperar`; 10 por hora
  por IP en `restablecer`.
- Brevo siempre simulado: sin configurar, o si falla, la respuesta es la misma.
  En producción, sin Brevo, el arranque lo avisa en el log una sola vez.

Necesitan Postgres, salvo las del principio (plantilla, configuración, aviso
del arranque y tokens).
Definí DATABASE_URL_TEST o se saltean solas.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

import httpx
import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app import email as correo
from app import ratelimit
from app.config import Config
from app.main import app
from app.models import RecuperacionContrasena, Usuario
from app.routers import cuentas as rutas_cuentas
from app.security import (
    ALGORITMO,
    al_milisegundo,
    config as config_seguridad,
    crear_token,
    hash_de_token,
    leer_sesion,
    verificar_password,
)
from tests.conftest import (
    EMAIL_ADMIN,
    EMAIL_BAJA,
    EMAIL_ORGANIZADOR,
    EMAIL_PENDIENTE,
    PASSWORD_ADMIN,
    PASSWORD_CUENTA,
    iniciar_sesion,
    nueva_cuenta,
    sin_base,
)
from tests.simulados import (
    CLAVE_BREVO,
    REMITENTE,
    URL_PANEL,
    BrevoFalso,
    pedir_directo,
    prohibido,
)
from tests.test_cuentas import afirmar_error, bearer, login
from tests.test_superadmin import bearer_de

LINK_VENCIDO = "El link ya no sirve. Pedí uno nuevo."
NUEVA = "una-clave-nueva-larga"
RESPUESTA = {"enviado": True}


@pytest.fixture(autouse=True)
def brevo(monkeypatch) -> BrevoFalso:
    """Brevo configurado y simulado; Cloudinary, prohibido. Nada sale de verdad."""
    falso = BrevoFalso()
    monkeypatch.setattr(httpx, "post", falso.post)
    monkeypatch.setattr(httpx, "delete", prohibido)
    monkeypatch.setattr(correo.config, "BREVO_API_KEY", CLAVE_BREVO)
    monkeypatch.setattr(correo.config, "EMAIL_REMITENTE", REMITENTE)
    monkeypatch.setattr(correo.config, "EMAIL_REMITENTE_NOMBRE", "Transmití tu foto")
    monkeypatch.setattr(correo.config, "URL_PANEL", URL_PANEL)
    correo.reiniciar_aviso()
    yield falso
    correo.reiniciar_aviso()


def recuperar(cliente, email: str, ip: str = "203.0.113.7"):
    return cliente.post("/api/cuentas/recuperar", json={"email": email},
                        headers={"X-Forwarded-For": ip})


def restablecer(cliente, token: str, password: str = NUEVA, ip: str = "203.0.113.7"):
    return cliente.post("/api/cuentas/restablecer", json={"token": token, "password": password},
                        headers={"X-Forwarded-For": ip})


def recuperaciones(db, usuario_id: int) -> list[RecuperacionContrasena]:
    db.expire_all()
    return list(db.scalars(
        select(RecuperacionContrasena)
        .where(RecuperacionContrasena.usuario_id == usuario_id)
        .order_by(RecuperacionContrasena.id)
    ))


def hash_guardado(db, usuario_id: int) -> str:
    db.expire_all()
    return db.scalar(select(Usuario.password_hash).where(Usuario.id == usuario_id))


# ─────────────────────────────────────────────────────────────
# Sin base: la plantilla, el link y la configuración
# ─────────────────────────────────────────────────────────────

def test_el_email_dice_lo_que_tiene_que_decir():
    asunto, contenido_html, texto = correo.email_de_recuperacion(
        "Bruno", f"{URL_PANEL}/admin/restablecer#token=abc"
    )
    assert "Transmití tu foto" in asunto
    for frase in ("Pediste cambiar tu contraseña de Transmití tu foto.",
                  "Tocá el botón para elegir una nueva.",
                  "El link sirve una vez y vence en una hora.",
                  "Si no fuiste vos, ignorá este email."):
        assert frase in contenido_html, frase
    for frase in ("Pediste cambiar tu contraseña de Transmití tu foto.",
                  "El link sirve una vez y vence en una hora.",
                  "Si no fuiste vos, ignorá este email."):
        assert frase in texto, frase
    assert f'href="{URL_PANEL}/admin/restablecer#token=abc"' in contenido_html
    assert f"{URL_PANEL}/admin/restablecer#token=abc" in texto
    assert "Hola, Bruno." in contenido_html and "Hola, Bruno." in texto
    assert "gradient" not in contenido_html, "colores planos, sin degradés"


def test_el_nombre_va_escapado_en_el_html():
    """El nombre lo elige quien se registra: sin escapar, metería su propio
    link en un email que sale con nuestro remitente."""
    malicioso = '<a href="https://malo.test">Ana</a> & "Co"'
    _, contenido_html, texto = correo.email_de_recuperacion(malicioso, f"{URL_PANEL}/x")
    assert "https://malo.test" not in re.findall(r'href="([^"]+)"', contenido_html)
    assert "<a href=\"https://malo.test\">" not in contenido_html
    assert "&lt;a href=&quot;https://malo.test&quot;&gt;Ana&lt;/a&gt; &amp; &quot;Co&quot;" in contenido_html
    assert malicioso in texto, "en el texto plano no hace falta escapar"


def test_el_token_va_en_el_fragmento_del_link():
    """Después de `#`: el navegador no lo manda en ningún pedido, así que no
    queda en ningún log de servidor."""
    enlace = correo.enlace_de_restablecer("TOKEN123")
    assert enlace == f"{URL_PANEL}/admin/restablecer#token=TOKEN123"
    assert "?" not in enlace


@pytest.mark.parametrize("cors,url_panel,esperada", [
    ("http://localhost:5173,https://transmitifoto.onrender.com", "",
     "https://transmitifoto.onrender.com"),
    ("https://uno.test/,https://dos.test", "", "https://uno.test"),
    ("http://localhost:5173", "", "http://localhost:5173"),
    ("http://localhost:5173,https://x.test", "https://panel.test/", "https://panel.test"),
])
def test_url_panel_por_defecto_es_el_primer_origen_https(cors, url_panel, esperada):
    assert Config(CORS_ORIGINS=cors, URL_PANEL=url_panel).url_panel == esperada


@pytest.mark.parametrize("clave,remitente,esperado", [
    ("k", "a@b.test", True), ("", "a@b.test", False), ("k", "", False), ("  ", "a@b.test", False),
])
def test_el_email_esta_configurado_con_clave_y_remitente(clave, remitente, esperado):
    assert Config(BREVO_API_KEY=clave, EMAIL_REMITENTE=remitente).email_configurado is esperado


def avisos_de_email(caplog) -> list[logging.LogRecord]:
    return [x for x in caplog.records if x.name == correo.log.name]


@pytest.mark.parametrize("falta", ["BREVO_API_KEY", "EMAIL_REMITENTE"])
def test_en_produccion_sin_brevo_el_arranque_avisa_una_vez(monkeypatch, caplog, falta):
    """El README manda a buscar `email: SIN CONFIGURAR` en el log de Render para
    saber si faltó cargar Brevo: tiene que salir al arrancar, sin esperar a que
    alguien pida un link. El Config es uno solo (lru_cache de obtener_config):
    el mismo que lee el lifespan. Dos arranques en el mismo proceso, un aviso."""
    monkeypatch.setattr(correo.config, "ENTORNO", "produccion")
    monkeypatch.setattr(correo.config, falta, "")
    correo.reiniciar_aviso()
    with caplog.at_level(logging.WARNING, logger=correo.log.name):
        for _ in range(2):
            with TestClient(app):
                pass
    avisos = avisos_de_email(caplog)
    assert [x.levelno for x in avisos] == [logging.WARNING], [x.getMessage() for x in avisos]
    assert avisos[0].getMessage().startswith("email: SIN CONFIGURAR")


@pytest.mark.parametrize("entorno,clave", [
    ("produccion", CLAVE_BREVO),  # configurado: nada que avisar
    ("desarrollo", ""),           # en desarrollo el arranque no avisa; recién al pedir un link
])
def test_el_arranque_no_avisa_de_mas(monkeypatch, caplog, entorno, clave):
    monkeypatch.setattr(correo.config, "ENTORNO", entorno)
    monkeypatch.setattr(correo.config, "BREVO_API_KEY", clave)
    correo.reiniciar_aviso()
    with caplog.at_level(logging.WARNING, logger=correo.log.name):
        with TestClient(app):
            pass
    assert avisos_de_email(caplog) == []


def test_el_token_de_sesion_lleva_milisegundos():
    momento = datetime.now(timezone.utc).replace(microsecond=123456)
    segundos = int(momento.replace(microsecond=0).timestamp())
    token, expira_en = crear_token(7, "x@x.test", emitido_en=momento)
    carga = jwt.decode(token, config_seguridad.JWT_SECRET, algorithms=[ALGORITMO])
    assert carga["iat"] == segundos + 0.123, "al milisegundo, sin los microsegundos"
    assert leer_sesion(token) == (7, segundos * 1000 + 123)
    assert expira_en == al_milisegundo(momento) + timedelta(hours=config_seguridad.JWT_HORAS)


def test_el_hash_del_token_es_sha256():
    assert hash_de_token("abc") == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


# ─────────────────────────────────────────────────────────────
# Recuperar: el email y lo que queda en la base
# ─────────────────────────────────────────────────────────────

@sin_base
def test_recuperar_manda_el_email_con_el_link(cliente_con_base, organizador, brevo, db):
    r = recuperar(cliente_con_base, EMAIL_ORGANIZADOR)
    assert r.status_code == 200, r.text
    assert r.json() == RESPUESTA

    assert len(brevo.envios) == 1
    envio = brevo.envios[0]
    assert envio["url"] == "https://api.brevo.com/v3/smtp/email"
    assert envio["headers"]["api-key"] == CLAVE_BREVO
    cuerpo = envio["json"]
    assert cuerpo["sender"] == {"name": "Transmití tu foto", "email": REMITENTE}
    assert cuerpo["to"] == [{"email": EMAIL_ORGANIZADOR, "name": "Bruno Organizador"}]
    assert cuerpo["subject"] == correo.ASUNTO_RECUPERACION
    token = brevo.token()
    enlace = f"{URL_PANEL}/admin/restablecer#token={token}"
    assert enlace in cuerpo["textContent"] and enlace in cuerpo["htmlContent"]
    assert len(token) >= 43, "256 bits al azar"

    [fila] = recuperaciones(db, organizador.id)
    assert fila.token_hash == hash_de_token(token)
    assert fila.token_hash != token, "en la base, sólo el hash"
    assert fila.vence_en - fila.creado_en == timedelta(hours=1)
    assert fila.usado_en is None and fila.anulado_en is None


@sin_base
def test_recuperar_compara_el_email_sin_mayusculas_ni_espacios(cliente_con_base, organizador,
                                                              brevo):
    r = recuperar(cliente_con_base, "  BRUNO@TransmitiFoto.TEST ")
    assert r.json() == RESPUESTA
    assert [e["json"]["to"][0]["email"] for e in brevo.envios] == [EMAIL_ORGANIZADOR]


@sin_base
def test_recuperar_responde_igual_exista_o_no_la_cuenta(cliente_con_base, organizador,
                                                       cuenta_pendiente, cuenta_baja, brevo, db):
    """Mismo código, mismo cuerpo byte por byte y las mismas cabeceras (salvo
    la fecha y el largo, que es el mismo): nada distingue a una cuenta que existe."""
    respuestas = {
        email: recuperar(cliente_con_base, email, ip=f"198.51.100.{i}")
        for i, email in enumerate(
            [EMAIL_ORGANIZADOR, "nadie@transmitifoto.test", EMAIL_PENDIENTE, EMAIL_BAJA]
        )
    }
    cuerpos = {r.content for r in respuestas.values()}
    assert {r.status_code for r in respuestas.values()} == {200}
    assert cuerpos == {b'{"enviado":true}'}
    cabeceras = {
        tuple(sorted((k, v) for k, v in r.headers.items() if k.lower() != "date"))
        for r in respuestas.values()
    }
    assert len(cabeceras) == 1, cabeceras

    assert [e["json"]["to"][0]["email"] for e in brevo.envios] == [EMAIL_ORGANIZADOR]


@sin_base
def test_una_cuenta_pendiente_o_de_baja_no_recibe_email(cliente_con_base, cuenta_pendiente,
                                                        cuenta_baja, brevo, db):
    """No podría entrar aunque cambiara la contraseña. Tampoco queda un token."""
    for email in (EMAIL_PENDIENTE, EMAIL_BAJA):
        assert recuperar(cliente_con_base, email).json() == RESPUESTA
    assert brevo.envios == []
    assert recuperaciones(db, cuenta_pendiente.id) == []
    assert recuperaciones(db, cuenta_baja.id) == []


@sin_base
def test_recuperar_con_algo_que_no_es_un_email(cliente_con_base, brevo):
    """422 por la forma, igual para cualquier texto: no dice nada de las cuentas."""
    for cuerpo in ({"email": "no-es-un-email"}, {"email": ""}, {}, {"email": "a" * 300 + "@x.test"}):
        r = cliente_con_base.post("/api/cuentas/recuperar", json=cuerpo)
        afirmar_error(r, "DATOS_INVALIDOS", 422)
    assert brevo.envios == []


@sin_base
def test_la_respuesta_sale_antes_que_el_email(cliente_con_base, organizador, brevo):
    """Con un Brevo que tarda 0,8 s, la respuesta sale igual enseguida y el email
    se manda después: esperar a Brevo haría tardar más justo a las cuentas que
    existen."""
    brevo.demora = 0.8
    existe = pedir_directo(app, "POST", "/api/cuentas/recuperar", {"email": EMAIL_ORGANIZADOR})
    assert existe.status == 200 and existe.cuerpo == b'{"enviado":true}'
    assert len(brevo.envios) == 1, "el email salió"
    assert existe.total_s >= 0.8, "la tarea de fondo esperó a Brevo"
    assert existe.respuesta_s < 0.5, f"la respuesta esperó al email: {existe.respuesta_s:.2f} s"


@sin_base
def test_sin_diferencias_de_tiempo_groseras(cliente_con_base, organizador, brevo):
    """Con un Brevo lento, una cuenta que existe y una que no tardan lo mismo en
    responder (con un margen amplio, para no depender de la máquina)."""
    brevo.demora = 0.6
    existe, no_existe = [], []
    for i in range(3):
        ratelimit.reiniciar()
        existe.append(pedir_directo(app, "POST", "/api/cuentas/recuperar",
                                    {"email": EMAIL_ORGANIZADOR}).respuesta_s)
        no_existe.append(pedir_directo(app, "POST", "/api/cuentas/recuperar",
                                       {"email": f"nadie{i}@transmitifoto.test"}).respuesta_s)
    diferencia = abs(sorted(existe)[1] - sorted(no_existe)[1])
    assert diferencia < 0.25, (existe, no_existe)
    assert len(brevo.envios) == 3


# ─────────────────────────────────────────────────────────────
# Brevo sin configurar o fallando
# ─────────────────────────────────────────────────────────────

@sin_base
@pytest.mark.parametrize("falta", ["BREVO_API_KEY", "EMAIL_REMITENTE"])
def test_sin_brevo_responde_igual_y_avisa_una_vez(cliente_con_base, organizador, brevo,
                                                  monkeypatch, caplog, falta):
    monkeypatch.setattr(correo.config, falta, "")
    with caplog.at_level(logging.INFO, logger=correo.log.name):
        for i in range(2):
            r = recuperar(cliente_con_base, EMAIL_ORGANIZADOR, ip=f"198.51.100.{i}")
            assert r.status_code == 200 and r.json() == RESPUESTA
    assert brevo.envios == [], "no sale ningún pedido"
    avisos = [x for x in caplog.records if x.name == correo.log.name]
    assert len(avisos) == 1, [x.getMessage() for x in avisos]
    assert avisos[0].levelno == logging.WARNING
    assert avisos[0].getMessage().startswith("email: SIN CONFIGURAR")


@sin_base
@pytest.mark.parametrize("falla", [
    lambda: httpx.Response(400, json={"code": "invalid_parameter", "message": "sender not valid"}),
    lambda: httpx.Response(401, json={"code": "unauthorized"}),
    lambda: httpx.ConnectError("sin red"),
    lambda: httpx.ReadTimeout("tardó"),
])
def test_si_brevo_falla_la_respuesta_es_la_misma(cliente_con_base, organizador, brevo, caplog,
                                                 falla):
    brevo.respuesta = falla
    with caplog.at_level(logging.INFO, logger=correo.log.name):
        r = recuperar(cliente_con_base, EMAIL_ORGANIZADOR)
    assert r.status_code == 200 and r.json() == RESPUESTA
    errores = [x for x in caplog.records if x.name == correo.log.name]
    assert [x.levelno for x in errores] == [logging.ERROR]
    assert errores[0].getMessage().startswith("email:")


@sin_base
def test_el_log_no_lleva_ni_el_email_ni_el_token(cliente_con_base, organizador, brevo, caplog):
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        recuperar(cliente_con_base, EMAIL_ORGANIZADOR)
        token = brevo.token()
        assert restablecer(cliente_con_base, token).status_code == 200
    mensajes = [x.getMessage() for x in caplog.records if x.name.startswith("uvicorn.error")]
    assert any(m.startswith("email: recuperación") for m in mensajes), mensajes
    assert any(m.startswith("cuentas:") and f"cuenta {organizador.id}" in m for m in mensajes)
    for dato in (EMAIL_ORGANIZADOR, token, "Bruno", NUEVA):
        assert dato not in caplog.text


# ─────────────────────────────────────────────────────────────
# Restablecer
# ─────────────────────────────────────────────────────────────

@sin_base
def test_restablecer_cambia_la_contrasena(cliente_con_base, organizador, brevo, db):
    recuperar(cliente_con_base, EMAIL_ORGANIZADOR)
    r = restablecer(cliente_con_base, brevo.token())
    assert r.status_code == 200, r.text
    assert r.json() == {"restablecida": True}

    assert verificar_password(NUEVA, hash_guardado(db, organizador.id))
    afirmar_error(login(cliente_con_base, EMAIL_ORGANIZADOR, PASSWORD_CUENTA), "NO_AUTORIZADO", 401)
    assert login(cliente_con_base, EMAIL_ORGANIZADOR, NUEVA).status_code == 200
    [fila] = recuperaciones(db, organizador.id)
    assert fila.usado_en is not None and fila.anulado_en is None


@sin_base
def test_el_link_sirve_una_sola_vez(cliente_con_base, organizador, brevo, db):
    recuperar(cliente_con_base, EMAIL_ORGANIZADOR)
    token = brevo.token()
    assert restablecer(cliente_con_base, token).status_code == 200
    hash_despues = hash_guardado(db, organizador.id)

    r = restablecer(cliente_con_base, token, password="otra-clave-mas-larga")
    afirmar_error(r, "DATOS_INVALIDOS", 422)
    assert r.json()["error"]["mensaje"] == LINK_VENCIDO
    assert hash_guardado(db, organizador.id) == hash_despues


@sin_base
def test_el_link_vence_a_la_hora(cliente_con_base, organizador, brevo, db):
    recuperar(cliente_con_base, EMAIL_ORGANIZADOR)
    token = brevo.token()
    [fila] = recuperaciones(db, organizador.id)
    assert fila.vence_en - fila.creado_en == timedelta(hours=1)

    # Un segundo antes de vencer, todavía no; ya vencido, no sirve.
    db.execute(update(RecuperacionContrasena).where(RecuperacionContrasena.id == fila.id)
               .values(vence_en=datetime.now(timezone.utc) - timedelta(seconds=1)))
    db.commit()
    antes = hash_guardado(db, organizador.id)
    r = restablecer(cliente_con_base, token)
    afirmar_error(r, "DATOS_INVALIDOS", 422)
    assert r.json()["error"]["mensaje"] == LINK_VENCIDO
    assert hash_guardado(db, organizador.id) == antes

    db.execute(update(RecuperacionContrasena).where(RecuperacionContrasena.id == fila.id)
               .values(vence_en=datetime.now(timezone.utc) + timedelta(seconds=30)))
    db.commit()
    assert restablecer(cliente_con_base, token).status_code == 200


@sin_base
def test_un_pedido_nuevo_anula_los_anteriores(cliente_con_base, organizador, brevo, db):
    recuperar(cliente_con_base, EMAIL_ORGANIZADOR)
    primero = brevo.token()
    recuperar(cliente_con_base, EMAIL_ORGANIZADOR)
    segundo = brevo.token()
    assert primero != segundo

    viejo, nuevo = recuperaciones(db, organizador.id)
    assert viejo.anulado_en is not None and nuevo.anulado_en is None

    r = restablecer(cliente_con_base, primero)
    afirmar_error(r, "DATOS_INVALIDOS", 422)
    assert r.json()["error"]["mensaje"] == LINK_VENCIDO
    assert restablecer(cliente_con_base, segundo).status_code == 200


@sin_base
def test_un_pedido_de_otra_cuenta_no_anula_los_de_esta(cliente_con_base, organizador,
                                                      otro_organizador, brevo):
    recuperar(cliente_con_base, EMAIL_ORGANIZADOR)
    de_bruno = brevo.token()
    recuperar(cliente_con_base, otro_organizador.email)
    assert restablecer(cliente_con_base, de_bruno).status_code == 200


@sin_base
@pytest.mark.parametrize("caso", [
    "inventado", "vacio", "el_hash_guardado", "un_token_de_sesion", "con_un_caracter_de_mas",
])
def test_un_token_que_no_sirve_da_siempre_el_mismo_error(cliente_con_base, organizador, brevo,
                                                         db, caso):
    recuperar(cliente_con_base, EMAIL_ORGANIZADOR)
    bueno = brevo.token()
    token = {
        "inventado": "x" * 43,
        "vacio": "",
        "el_hash_guardado": hash_de_token(bueno),
        "un_token_de_sesion": crear_token(organizador.id, organizador.email)[0][:200],
        "con_un_caracter_de_mas": bueno + "A",
    }[caso]
    antes = hash_guardado(db, organizador.id)

    r = restablecer(cliente_con_base, token)
    afirmar_error(r, "DATOS_INVALIDOS", 422)
    assert r.json()["error"]["mensaje"] == LINK_VENCIDO
    assert hash_guardado(db, organizador.id) == antes
    assert restablecer(cliente_con_base, bueno).status_code == 200, "el bueno sigue sirviendo"


@sin_base
@pytest.mark.parametrize("estado", ["baja", "pendiente"])
def test_el_link_de_una_cuenta_que_ya_no_esta_activa(cliente_con_base, organizador, brevo, db,
                                                     estado):
    recuperar(cliente_con_base, EMAIL_ORGANIZADOR)
    token = brevo.token()
    db.execute(update(Usuario).where(Usuario.id == organizador.id).values(estado=estado))
    db.commit()
    antes = hash_guardado(db, organizador.id)

    r = restablecer(cliente_con_base, token)
    afirmar_error(r, "DATOS_INVALIDOS", 422)
    assert r.json()["error"]["mensaje"] == LINK_VENCIDO
    assert hash_guardado(db, organizador.id) == antes


@sin_base
@pytest.mark.parametrize("password", ["corta-9ch", "x" * 129, ""])
def test_una_contrasena_nueva_invalida_no_gasta_el_link(cliente_con_base, organizador, brevo, db,
                                                        password):
    recuperar(cliente_con_base, EMAIL_ORGANIZADOR)
    token = brevo.token()
    antes = hash_guardado(db, organizador.id)

    afirmar_error(restablecer(cliente_con_base, token, password=password), "DATOS_INVALIDOS", 422)
    assert hash_guardado(db, organizador.id) == antes
    [fila] = recuperaciones(db, organizador.id)
    assert fila.usado_en is None
    assert restablecer(cliente_con_base, token).status_code == 200, "el link sigue sirviendo"


@sin_base
def test_los_bordes_de_la_contrasena_nueva(cliente_con_base, organizador, brevo):
    for password in ("x" * 10, "y" * 128):
        ratelimit.reiniciar()
        recuperar(cliente_con_base, EMAIL_ORGANIZADOR)
        assert restablecer(cliente_con_base, brevo.token(), password=password).status_code == 200


# ─────────────────────────────────────────────────────────────
# Sesiones que se cierran
# ─────────────────────────────────────────────────────────────

@sin_base
def test_restablecer_cierra_todas_las_sesiones(cliente_con_base, organizador, brevo):
    en_la_compu = iniciar_sesion(cliente_con_base, EMAIL_ORGANIZADOR, PASSWORD_CUENTA)
    en_el_celular = iniciar_sesion(cliente_con_base, EMAIL_ORGANIZADOR, PASSWORD_CUENTA)
    for token in (en_la_compu, en_el_celular):
        assert cliente_con_base.get("/api/admin/yo", headers=bearer(token)).status_code == 200

    recuperar(cliente_con_base, EMAIL_ORGANIZADOR)
    assert restablecer(cliente_con_base, brevo.token()).status_code == 200

    for token in (en_la_compu, en_el_celular):
        for ruta in ("/api/admin/yo", "/api/admin/eventos"):
            afirmar_error(cliente_con_base.get(ruta, headers=bearer(token)), "NO_AUTORIZADO", 401)
    nueva = iniciar_sesion(cliente_con_base, EMAIL_ORGANIZADOR, NUEVA)
    assert cliente_con_base.get("/api/admin/yo", headers=bearer(nueva)).status_code == 200


@sin_base
def test_restablecer_no_toca_las_sesiones_de_otras_cuentas(cliente_con_base, organizador, brevo):
    de_ana = iniciar_sesion(cliente_con_base, EMAIL_ADMIN, PASSWORD_ADMIN)
    recuperar(cliente_con_base, EMAIL_ORGANIZADOR)
    assert restablecer(cliente_con_base, brevo.token()).status_code == 200
    assert cliente_con_base.get("/api/admin/yo", headers=bearer(de_ana)).status_code == 200


@sin_base
def test_un_token_anterior_a_sesiones_desde_no_sirve(cliente_con_base, organizador, db):
    """Al milisegundo: uno emitido 1 ms antes no sirve; uno emitido en el mismo
    milisegundo, sí (es el de quien cambió la contraseña)."""
    corte = al_milisegundo(datetime.now(timezone.utc))
    db.execute(update(Usuario).where(Usuario.id == organizador.id).values(sesiones_desde=corte))
    db.commit()

    def yo_con(momento):
        token, _ = crear_token(organizador.id, organizador.email, emitido_en=momento)
        return cliente_con_base.get("/api/admin/yo", headers=bearer(token))

    afirmar_error(yo_con(corte - timedelta(milliseconds=1)), "NO_AUTORIZADO", 401)
    afirmar_error(yo_con(corte - timedelta(hours=2)), "NO_AUTORIZADO", 401)
    assert yo_con(corte).status_code == 200
    assert yo_con(corte + timedelta(milliseconds=1)).status_code == 200


@sin_base
def test_un_token_sin_iat_no_sirve_si_se_cerraron_las_sesiones(cliente_con_base, organizador, db):
    sin_iat = jwt.encode(
        {"sub": str(organizador.id), "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        config_seguridad.JWT_SECRET, algorithm=ALGORITMO,
    )
    assert cliente_con_base.get("/api/admin/yo", headers=bearer(sin_iat)).status_code == 200
    db.execute(update(Usuario).where(Usuario.id == organizador.id)
               .values(sesiones_desde=al_milisegundo(datetime.now(timezone.utc))))
    db.commit()
    afirmar_error(cliente_con_base.get("/api/admin/yo", headers=bearer(sin_iat)),
                  "NO_AUTORIZADO", 401)


@sin_base
def test_sin_sesiones_desde_los_tokens_viejos_siguen(cliente_con_base, organizador):
    """Las cuentas migradas nacen con sesiones_desde en NULL: nadie queda afuera."""
    viejo, _ = crear_token(organizador.id, organizador.email,
                           emitido_en=datetime.now(timezone.utc) - timedelta(hours=11))
    assert cliente_con_base.get("/api/admin/yo", headers=bearer(viejo)).status_code == 200


# ─────────────────────────────────────────────────────────────
# Topes de pedidos
# ─────────────────────────────────────────────────────────────

@sin_base
def test_recuperar_tiene_tope_por_ip(cliente_con_base, organizador, brevo):
    for i in range(rutas_cuentas.MAXIMO_RECUPERACIONES_POR_IP):
        assert recuperar(cliente_con_base, f"serie{i}@x.test").status_code == 200
    r = recuperar(cliente_con_base, EMAIL_ORGANIZADOR)
    afirmar_error(r, "DEMASIADOS_PEDIDOS", 429)
    assert brevo.envios == [], "frenado antes de buscar la cuenta"
    assert recuperar(cliente_con_base, EMAIL_ORGANIZADOR, ip="198.51.100.9").status_code == 200


@sin_base
@pytest.mark.parametrize("email", [EMAIL_ORGANIZADOR, "nadie@transmitifoto.test"])
def test_recuperar_tiene_tope_por_email_exista_o_no(cliente_con_base, organizador, brevo, email):
    """Tres por hora por email, desde cualquier IP. Frena igual a un email que
    no existe: el 429 no dice nada de las cuentas."""
    for i in range(rutas_cuentas.MAXIMO_RECUPERACIONES_POR_EMAIL):
        assert recuperar(cliente_con_base, email, ip=f"198.51.100.{i}").status_code == 200
    r = recuperar(cliente_con_base, email.upper(), ip="192.0.2.99")
    afirmar_error(r, "DEMASIADOS_PEDIDOS", 429)
    assert len(brevo.envios) == (3 if email == EMAIL_ORGANIZADOR else 0)


def test_los_topes_de_recuperar_duran_una_hora():
    claves = [
        (("1.2.3.4", rutas_cuentas._CLAVE_RECUPERAR), rutas_cuentas.MAXIMO_RECUPERACIONES_POR_IP),
        ((rutas_cuentas._CLAVE_RECUPERAR, "a@x.test"), rutas_cuentas.MAXIMO_RECUPERACIONES_POR_EMAIL),
    ]
    ventana = rutas_cuentas.VENTANA_RECUPERACION
    assert ventana == 3600
    for _ in range(rutas_cuentas.MAXIMO_RECUPERACIONES_POR_EMAIL):
        assert ratelimit.permitido_en_todas(claves, ahora=0.0, ventana=ventana)
    ratelimit.limpiar_vencidos(ahora=ratelimit.VENTANA_SEGUNDOS + 1)
    assert not ratelimit.permitido_en_todas(claves, ahora=ratelimit.VENTANA_SEGUNDOS + 2,
                                            ventana=ventana)
    assert ratelimit.permitido_en_todas(claves, ahora=ventana + 1, ventana=ventana)


@sin_base
def test_restablecer_tiene_tope_por_ip(cliente_con_base, organizador, brevo):
    recuperar(cliente_con_base, EMAIL_ORGANIZADOR)
    bueno = brevo.token()
    for i in range(rutas_cuentas.MAXIMO_RESTABLECER_POR_IP):
        afirmar_error(restablecer(cliente_con_base, f"malo{i}"), "DATOS_INVALIDOS", 422)
    afirmar_error(restablecer(cliente_con_base, bueno), "DEMASIADOS_PEDIDOS", 429)
    assert restablecer(cliente_con_base, bueno, ip="198.51.100.9").status_code == 200


# ─────────────────────────────────────────────────────────────
# Con otras partes del sistema
# ─────────────────────────────────────────────────────────────

@sin_base
def test_eliminar_la_cuenta_se_lleva_sus_pedidos(cliente_con_base, organizador, superadmin,
                                                 brevo, db):
    """ON DELETE CASCADE: el DELETE de la cuenta no choca con sus pedidos."""
    id_bruno = organizador.id
    recuperar(cliente_con_base, EMAIL_ORGANIZADOR)
    token = brevo.token()
    assert len(recuperaciones(db, id_bruno)) == 1

    r = cliente_con_base.request(
        "DELETE", f"/api/admin/cuentas/{id_bruno}",
        json={"confirmar_email": EMAIL_ORGANIZADOR}, headers=bearer_de(superadmin),
    )
    assert r.status_code == 200, r.text
    db.expunge_all()
    assert recuperaciones(db, id_bruno) == []
    afirmar_error(restablecer(cliente_con_base, token), "DATOS_INVALIDOS", 422)


@sin_base
def test_el_token_de_sesion_no_sirve_para_restablecer_ni_al_reves(cliente_con_base, organizador,
                                                                  brevo):
    recuperar(cliente_con_base, EMAIL_ORGANIZADOR)
    token = brevo.token()
    afirmar_error(cliente_con_base.get("/api/admin/yo", headers=bearer(token)), "NO_AUTORIZADO", 401)


@sin_base
def test_las_rutas_publicas_no_piden_sesion(cliente_con_base, organizador, brevo):
    """Quien olvidó la contraseña no tiene sesión: las dos van sin Bearer."""
    assert "Authorization" not in cliente_con_base.headers
    assert recuperar(cliente_con_base, EMAIL_ORGANIZADOR).status_code == 200
    assert restablecer(cliente_con_base, brevo.token()).status_code == 200


@sin_base
def test_una_cuenta_creada_a_mano_con_mayusculas(cliente_con_base, db, brevo):
    """El registro guarda en minúsculas, pero una cuenta hecha a mano puede no
    estarlo. Se compara sin mayúsculas y el email sale a la dirección guardada."""
    nueva_cuenta(db, "Gabi.Manual@TransmitiFoto.test", "Gabi")
    recuperar(cliente_con_base, "gabi.manual@transmitifoto.test")
    assert brevo.envios[0]["json"]["to"][0]["email"] == "Gabi.Manual@TransmitiFoto.test"
