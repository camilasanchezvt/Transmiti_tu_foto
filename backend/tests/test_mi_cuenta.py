"""Mi cuenta (/api/admin/yo) y el estilo de la pantalla de cada evento.

Las reglas, en el orden del archivo:

- GET /api/admin/yo trae el avatar, el tema y los predeterminados. PATCH los
  cambia de a partes (al menos un valor), nunca el email, el rol ni el estado.
- Cambiar la contraseña pide la actual (con tope de pedidos), cierra todas las
  sesiones y devuelve una nueva para quien la cambió. Anula los links de
  "olvidé mi contraseña" que seguían vivos.
- El avatar se sube directo a Cloudinary con una firma para `avatares/{id}`.
  Guardarlo verifica la carpeta (PUBLIC_ID_AJENO) y la URL (ARCHIVO_INVALIDO).
  El anterior se borra de Cloudinary a mejor esfuerzo, y al eliminar una
  cuenta con avatar se borra toda su carpeta.
- Un evento nuevo nace con los predeterminados de su DUEÑO, también si un
  admin lo crea para otra cuenta. El estilo de pantalla viaja en EventoAdmin,
  se cambia con el PATCH del evento y llega a la config pública de la pantalla.

Cloudinary y Brevo siempre simulados. Necesitan Postgres, salvo las del
principio. Definí DATABASE_URL_TEST o se saltean solas.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app import cloudinary_service as cs
from app import email as correo
from app.config import obtener_config
from app.main import app
from app.models import Evento, Usuario
from app.routers import admin as rutas_admin
from app.routers.admin import hoy_en_argentina
from app.security import verificar_password
from tests.conftest import (
    EMAIL_ADMIN,
    EMAIL_ORGANIZADOR,
    PASSWORD_ADMIN,
    PASSWORD_CUENTA,
    iniciar_sesion,
    sin_base,
)
from tests.simulados import CLAVE_BREVO, REMITENTE, URL_PANEL, BrevoFalso, NubeFalsa
from tests.test_cuentas import afirmar_error, bearer, login, nuevo_evento
from tests.test_superadmin import bearer_de

NUBE = "nube-falsa"
CLAVE = "clave-falsa"
SECRETO = "secreto-de-prueba-que-no-sale"

ESTILO_POR_DEFECTO = {
    "pantalla_fondo": "desenfocado",
    "pantalla_transicion": "fundido",
    "pantalla_mostrar_nombre": True,
    "pantalla_mostrar_qr": True,
}


@pytest.fixture(autouse=True)
def nube(monkeypatch) -> NubeFalsa:
    """Cloudinary con credenciales de mentira y un DELETE simulado; Brevo
    configurado y simulado. Nada sale de verdad."""
    falsa = NubeFalsa()
    monkeypatch.setattr(httpx, "delete", falsa.delete)
    monkeypatch.setattr(cs.config, "CLOUDINARY_CLOUD_NAME", NUBE)
    monkeypatch.setattr(cs.config, "CLOUDINARY_API_KEY", CLAVE)
    monkeypatch.setattr(cs.config, "CLOUDINARY_API_SECRET", SECRETO)
    return falsa


@pytest.fixture(autouse=True)
def brevo(monkeypatch) -> BrevoFalso:
    falso = BrevoFalso()
    monkeypatch.setattr(httpx, "post", falso.post)
    monkeypatch.setattr(correo.config, "BREVO_API_KEY", CLAVE_BREVO)
    monkeypatch.setattr(correo.config, "EMAIL_REMITENTE", REMITENTE)
    monkeypatch.setattr(correo.config, "URL_PANEL", URL_PANEL)
    return falso


def url_avatar(public_id: str, nube: str = NUBE, extension: str = "jpg") -> str:
    return f"https://res.cloudinary.com/{nube}/image/upload/v1790000000/{public_id}.{extension}"


def guardar_avatar(cliente, public_id: str, url: str | None = None, headers=None):
    return cliente.put("/api/admin/yo/avatar",
                       json={"public_id": public_id, "url": url or url_avatar(public_id)},
                       headers=headers)


def cuenta_en_la_base(db, id_cuenta: int) -> Usuario:
    db.expunge_all()
    return db.get(Usuario, id_cuenta)


# ─────────────────────────────────────────────────────────────
# Sin base: /docs y CORS
# ─────────────────────────────────────────────────────────────

def test_docs_publica_mi_cuenta():
    esquema = TestClient(app).get("/openapi.json").json()
    componentes = esquema["components"]["schemas"]
    assert set(componentes["UsuarioYo"]["properties"]) == {
        "id", "email", "nombre", "rol", "avatar_url", "tema", "predeterminados",
    }
    assert set(componentes["Predeterminados"]["properties"]) == {
        "segundos_por_foto", "max_fotos_por_dispositivo", "pantalla",
    }
    assert set(componentes["EstiloPantalla"]["properties"]) == {
        "fondo", "transicion", "mostrar_nombre", "mostrar_qr",
    }
    assert set(componentes["CambioYo"]["properties"]) == {"nombre", "tema", "predeterminados"}
    assert componentes["CambioYo"]["additionalProperties"] is False
    assert set(componentes["AvatarNuevo"]["properties"]) == {"public_id", "url"}
    rutas = esquema["paths"]
    assert set(rutas["/api/admin/yo"]) == {"get", "patch"}
    assert rutas["/api/admin/yo/contrasena"]["post"]["responses"]["200"]["content"][
        "application/json"]["schema"]["$ref"] == "#/components/schemas/Sesion"
    assert {"400", "403", "422"} <= set(rutas["/api/admin/yo/avatar"]["put"]["responses"])
    for campo in ESTILO_POR_DEFECTO:
        assert campo in componentes["EventoAdmin"]["properties"]
        assert campo in componentes["CambioEstadoEvento"]["properties"]
    assert {"fondo", "transicion", "mostrar_nombre", "mostrar_qr"} <= set(
        componentes["PantallaConfig"]["properties"]
    )


def test_cors_deja_pasar_el_put():
    """PUT /api/admin/yo/avatar: sin PUT en allow_methods, el navegador corta el
    pedido en el preflight."""
    origenes = obtener_config().origenes_cors
    if not origenes:
        pytest.skip("sin CORS_ORIGINS")
    r = TestClient(app).options(
        "/api/admin/yo/avatar",
        headers={
            "Origin": origenes[0],
            "Access-Control-Request-Method": "PUT",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert r.status_code == 200, r.text
    assert "PUT" in r.headers["access-control-allow-methods"]


def test_la_carpeta_de_avatares_no_se_arma_con_cualquier_cosa():
    assert cs.carpeta_de_avatares(12) == "avatares/12"
    for malo in (0, -1, "12", True, None, 1.5):
        with pytest.raises(ValueError):
            cs.carpeta_de_avatares(malo)


# ─────────────────────────────────────────────────────────────
# GET y PATCH /api/admin/yo
# ─────────────────────────────────────────────────────────────

@sin_base
def test_yo_trae_mi_cuenta_completa(autorizado_organizador, organizador, db):
    db.execute(update(Usuario).where(Usuario.id == organizador.id).values(
        avatar_public_id=f"avatares/{organizador.id}/abc",
        avatar_url=url_avatar(f"avatares/{organizador.id}/abc"),
        tema="oscuro", pred_segundos_por_foto=9, pred_max_fotos_por_dispositivo=4,
        pred_pantalla_fondo="negro", pred_pantalla_transicion="corte",
        pred_pantalla_nombre=False, pred_pantalla_qr=True,
    ))
    db.commit()
    assert autorizado_organizador.get("/api/admin/yo").json() == {
        "id": organizador.id,
        "email": EMAIL_ORGANIZADOR,
        "nombre": "Bruno Organizador",
        "rol": "organizador",
        "avatar_url": url_avatar(f"avatares/{organizador.id}/abc"),
        "tema": "oscuro",
        "predeterminados": {
            "segundos_por_foto": 9,
            "max_fotos_por_dispositivo": 4,
            "pantalla": {"fondo": "negro", "transicion": "corte",
                         "mostrar_nombre": False, "mostrar_qr": True},
        },
    }


@sin_base
def test_cambiar_mi_nombre_y_mi_tema(autorizado_organizador, organizador, db):
    r = autorizado_organizador.patch("/api/admin/yo",
                                     json={"nombre": "  Bruno Nuevo  ", "tema": "claro"})
    assert r.status_code == 200, r.text
    assert r.json()["nombre"] == "Bruno Nuevo" and r.json()["tema"] == "claro"
    assert r.json() == autorizado_organizador.get("/api/admin/yo").json(), "lo mismo que GET"
    cuenta = cuenta_en_la_base(db, organizador.id)
    assert (cuenta.nombre, cuenta.tema) == ("Bruno Nuevo", "claro")


@sin_base
@pytest.mark.parametrize("tema", ["oscuro", "claro", "automatico"])
def test_los_tres_temas(autorizado_organizador, tema):
    assert autorizado_organizador.patch("/api/admin/yo", json={"tema": tema}).json()["tema"] == tema


@sin_base
def test_los_predeterminados_se_cambian_de_a_partes(autorizado_organizador, organizador, db):
    r = autorizado_organizador.patch("/api/admin/yo",
                                     json={"predeterminados": {"pantalla": {"fondo": "negro"}}})
    assert r.status_code == 200, r.text
    assert r.json()["predeterminados"] == {
        "segundos_por_foto": 7, "max_fotos_por_dispositivo": 10,
        "pantalla": {"fondo": "negro", "transicion": "fundido",
                     "mostrar_nombre": True, "mostrar_qr": True},
    }
    assert r.json()["tema"] == "automatico" and r.json()["nombre"] == "Bruno Organizador"

    r = autorizado_organizador.patch("/api/admin/yo", json={"predeterminados": {
        "segundos_por_foto": 12, "max_fotos_por_dispositivo": 3,
        "pantalla": {"transicion": "corte", "mostrar_nombre": False, "mostrar_qr": False},
    }})
    assert r.json()["predeterminados"] == {
        "segundos_por_foto": 12, "max_fotos_por_dispositivo": 3,
        "pantalla": {"fondo": "negro", "transicion": "corte",
                     "mostrar_nombre": False, "mostrar_qr": False},
    }
    cuenta = cuenta_en_la_base(db, organizador.id)
    assert (cuenta.pred_segundos_por_foto, cuenta.pred_max_fotos_por_dispositivo,
            cuenta.pred_pantalla_fondo, cuenta.pred_pantalla_transicion,
            cuenta.pred_pantalla_nombre, cuenta.pred_pantalla_qr) == (
        12, 3, "negro", "corte", False, False)


@sin_base
def test_los_bordes_de_los_predeterminados(autorizado_organizador):
    for segundos, fotos in ((3, 1), (30, 50)):
        r = autorizado_organizador.patch("/api/admin/yo", json={"predeterminados": {
            "segundos_por_foto": segundos, "max_fotos_por_dispositivo": fotos}})
        assert r.status_code == 200, r.text


@sin_base
@pytest.mark.parametrize("cuerpo", [
    {},
    {"tema": None},
    {"predeterminados": {}},
    {"predeterminados": {"pantalla": {}}},
    {"tema": "sepia"},
    {"nombre": "   "},
    {"nombre": "x" * 81},
    {"predeterminados": {"segundos_por_foto": 2}},
    {"predeterminados": {"segundos_por_foto": 31}},
    {"predeterminados": {"max_fotos_por_dispositivo": 0}},
    {"predeterminados": {"max_fotos_por_dispositivo": 51}},
    {"predeterminados": {"pantalla": {"fondo": "blanco"}}},
    {"predeterminados": {"pantalla": {"transicion": "zoom"}}},
    {"predeterminados": {"pantalla": {"mostrar_qr": "tal vez"}}},
    {"predeterminados": {"segundos": 5}},
    {"predeterminados": {"pantalla": {"color": "rojo"}}},
    {"email": "otro@transmitifoto.test"},
    {"rol": "admin"},
    {"estado": "baja"},
    {"nombre": "Bruno Admin", "rol": "superadmin"},
    {"avatar_url": "https://malo.test/x.jpg"},
])
def test_cambios_de_mi_cuenta_invalidos(autorizado_organizador, organizador, db, cuerpo):
    """Un campo que no existe (email, rol, estado, avatar_url) es 422 y no se
    ignora: así no parece que cambió. En cada rechazo no se toca nada."""
    antes = autorizado_organizador.get("/api/admin/yo").json()
    afirmar_error(autorizado_organizador.patch("/api/admin/yo", json=cuerpo), "DATOS_INVALIDOS", 422)
    assert autorizado_organizador.get("/api/admin/yo").json() == antes
    cuenta = cuenta_en_la_base(db, organizador.id)
    assert (cuenta.rol, cuenta.estado, cuenta.email) == ("organizador", "activa", EMAIL_ORGANIZADOR)


@sin_base
def test_cambiar_mi_cuenta_es_idempotente(autorizado_organizador):
    cambio = {"tema": "oscuro", "predeterminados": {"pantalla": {"mostrar_qr": False}}}
    primera = autorizado_organizador.patch("/api/admin/yo", json=cambio)
    segunda = autorizado_organizador.patch("/api/admin/yo", json=cambio)
    assert primera.status_code == segunda.status_code == 200
    assert primera.json() == segunda.json()


@sin_base
def test_mi_cuenta_no_toca_la_de_otro(autorizado, autorizado_organizador, db):
    autorizado_organizador.patch("/api/admin/yo", json={
        "tema": "claro", "predeterminados": {"segundos_por_foto": 20}})
    de_ana = autorizado.get("/api/admin/yo").json()
    assert de_ana["tema"] == "automatico"
    assert de_ana["predeterminados"]["segundos_por_foto"] == 7


@sin_base
def test_un_admin_tambien_cambia_su_cuenta_y_no_su_rol(autorizado, db):
    afirmar_error(autorizado.patch("/api/admin/yo", json={"rol": "organizador"}),
                  "DATOS_INVALIDOS", 422)
    r = autorizado.patch("/api/admin/yo", json={"nombre": "Ana"})
    assert r.status_code == 200 and r.json()["rol"] == "admin"


# ─────────────────────────────────────────────────────────────
# Cambiar la contraseña
# ─────────────────────────────────────────────────────────────

def cambiar_contrasena(cliente, actual: str, nueva: str, headers=None):
    return cliente.post("/api/admin/yo/contrasena", json={"actual": actual, "nueva": nueva},
                        headers=headers)


@sin_base
def test_cambiar_la_contrasena_cierra_las_otras_sesiones_y_sigue_adentro(cliente_con_base,
                                                                        organizador, db):
    en_la_compu = iniciar_sesion(cliente_con_base, EMAIL_ORGANIZADOR, PASSWORD_CUENTA)
    en_el_celular = iniciar_sesion(cliente_con_base, EMAIL_ORGANIZADOR, PASSWORD_CUENTA)

    r = cambiar_contrasena(cliente_con_base, PASSWORD_CUENTA, "otra-clave-larga",
                           headers=bearer(en_la_compu))
    assert r.status_code == 200, r.text
    assert set(r.json()) == {"token", "expira_en"}
    nuevo = r.json()["token"]
    vence = datetime.fromisoformat(r.json()["expira_en"])
    assert timedelta(hours=11, minutes=59) < vence - datetime.now(timezone.utc) <= timedelta(hours=12)

    # Quien la cambió sigue adentro con el token nuevo; las sesiones viejas,
    # también la suya, ya no sirven.
    assert cliente_con_base.get("/api/admin/yo", headers=bearer(nuevo)).status_code == 200
    for viejo in (en_la_compu, en_el_celular):
        afirmar_error(cliente_con_base.get("/api/admin/yo", headers=bearer(viejo)),
                      "NO_AUTORIZADO", 401)

    assert verificar_password("otra-clave-larga", cuenta_en_la_base(db, organizador.id).password_hash)
    afirmar_error(login(cliente_con_base, EMAIL_ORGANIZADOR, PASSWORD_CUENTA), "NO_AUTORIZADO", 401)
    assert login(cliente_con_base, EMAIL_ORGANIZADOR, "otra-clave-larga").status_code == 200


@sin_base
def test_con_la_contrasena_actual_mal_no_cambia_nada(autorizado_organizador, organizador, db):
    antes = cuenta_en_la_base(db, organizador.id).password_hash
    r = cambiar_contrasena(autorizado_organizador, "no-es-la-actual", "otra-clave-larga")
    afirmar_error(r, "DATOS_INVALIDOS", 422)
    assert r.json()["error"]["mensaje"] == "La contraseña actual no es correcta"
    cuenta = cuenta_en_la_base(db, organizador.id)
    assert cuenta.password_hash == antes and cuenta.sesiones_desde is None
    assert autorizado_organizador.get("/api/admin/yo").status_code == 200, "la sesión sigue"


@sin_base
@pytest.mark.parametrize("cuerpo", [
    {"actual": PASSWORD_CUENTA, "nueva": "corta-9ch"},
    {"actual": PASSWORD_CUENTA, "nueva": "x" * 129},
    {"actual": "", "nueva": "otra-clave-larga"},
    {"actual": PASSWORD_CUENTA},
    {"nueva": "otra-clave-larga"},
])
def test_cambiar_la_contrasena_con_datos_invalidos(autorizado_organizador, organizador, db, cuerpo):
    antes = cuenta_en_la_base(db, organizador.id).password_hash
    afirmar_error(autorizado_organizador.post("/api/admin/yo/contrasena", json=cuerpo),
                  "DATOS_INVALIDOS", 422)
    assert cuenta_en_la_base(db, organizador.id).password_hash == antes


@sin_base
def test_cambiar_la_contrasena_tiene_tope(autorizado_organizador, autorizado, organizador, db):
    """Cinco por hora y por cuenta: una sesión robada no sirve para adivinar la
    contraseña actual. El sexto intento se frena aunque la actual sea correcta,
    y no le gasta el cupo a otra cuenta."""
    for _ in range(rutas_admin.MAXIMO_CAMBIOS_DE_CONTRASENA):
        afirmar_error(cambiar_contrasena(autorizado_organizador, "probando-una", "otra-clave-larga"),
                      "DATOS_INVALIDOS", 422)
    r = cambiar_contrasena(autorizado_organizador, PASSWORD_CUENTA, "otra-clave-larga")
    afirmar_error(r, "DEMASIADOS_PEDIDOS", 429)
    assert verificar_password(PASSWORD_CUENTA, cuenta_en_la_base(db, organizador.id).password_hash)

    assert cambiar_contrasena(autorizado, PASSWORD_ADMIN, "otra-clave-de-ana").status_code == 200


@sin_base
def test_cambiar_la_contrasena_anula_los_links_de_recuperacion(cliente_con_base, organizador,
                                                               brevo):
    cliente_con_base.post("/api/cuentas/recuperar", json={"email": EMAIL_ORGANIZADOR})
    token_del_email = brevo.token()
    sesion = iniciar_sesion(cliente_con_base, EMAIL_ORGANIZADOR, PASSWORD_CUENTA)
    assert cambiar_contrasena(cliente_con_base, PASSWORD_CUENTA, "otra-clave-larga",
                              headers=bearer(sesion)).status_code == 200

    r = cliente_con_base.post("/api/cuentas/restablecer",
                              json={"token": token_del_email, "password": "la-del-link-1234"})
    afirmar_error(r, "DATOS_INVALIDOS", 422)
    assert login(cliente_con_base, EMAIL_ORGANIZADOR, "otra-clave-larga").status_code == 200


# ─────────────────────────────────────────────────────────────
# Avatar
# ─────────────────────────────────────────────────────────────

@sin_base
def test_firma_del_avatar(autorizado_organizador, organizador):
    r = autorizado_organizador.post("/api/admin/yo/avatar/firma")
    assert r.status_code == 200, r.text
    firma = r.json()
    assert set(firma) == {"cloud_name", "api_key", "timestamp", "signature", "folder"}
    assert firma["folder"] == f"avatares/{organizador.id}"
    assert (firma["cloud_name"], firma["api_key"]) == (NUBE, CLAVE)
    a_firmar = f"folder=avatares/{organizador.id}&timestamp={firma['timestamp']}{SECRETO}"
    assert firma["signature"] == hashlib.sha1(a_firmar.encode()).hexdigest()
    assert SECRETO not in r.text, "regla 2: el secreto no sale del backend"


@sin_base
def test_la_firma_del_avatar_tiene_tope(autorizado_organizador, autorizado):
    for _ in range(rutas_admin.MAXIMO_FIRMAS_DE_AVATAR):
        assert autorizado_organizador.post("/api/admin/yo/avatar/firma").status_code == 200
    afirmar_error(autorizado_organizador.post("/api/admin/yo/avatar/firma"),
                  "DEMASIADOS_PEDIDOS", 429)
    assert autorizado.post("/api/admin/yo/avatar/firma").status_code == 200, "es por cuenta"


@sin_base
def test_guardar_el_avatar(autorizado_organizador, autorizado, organizador, nube, db):
    public_id = f"avatares/{organizador.id}/k3j2h1"
    r = guardar_avatar(autorizado_organizador, public_id)
    assert r.status_code == 200, r.text
    assert r.json()["avatar_url"] == url_avatar(public_id)
    assert r.json() == autorizado_organizador.get("/api/admin/yo").json()
    cuenta = cuenta_en_la_base(db, organizador.id)
    assert (cuenta.avatar_public_id, cuenta.avatar_url) == (public_id, url_avatar(public_id))
    assert nube.pedidos == [], "no había uno anterior que borrar"

    cuentas = {c["email"]: c for c in autorizado.get("/api/admin/cuentas").json()}
    assert cuentas[EMAIL_ORGANIZADOR]["avatar_url"] == url_avatar(public_id)
    assert cuentas[EMAIL_ADMIN]["avatar_url"] is None


@sin_base
@pytest.mark.parametrize("extension", ["jpg", "jpeg", "png", "webp", "heic", "JPG"])
def test_el_avatar_acepta_las_extensiones_de_foto(autorizado_organizador, organizador, extension):
    public_id = f"avatares/{organizador.id}/foto_1-a"
    r = guardar_avatar(autorizado_organizador, public_id,
                       url_avatar(public_id, extension=extension))
    assert r.status_code == 200, r.text


@sin_base
@pytest.mark.parametrize("carpeta", [
    "avatares/{ana}/abc",
    "eventos/ab12cd34/abc",
    "avatares/{bruno}/sub/abc",
    "avatares/{bruno}/",
    "avatares/{bruno}",
    "avatares/{bruno}0/abc",
    "avatares/{bruno}/../{ana}/abc",
    "avatares/{bruno}/abc.jpg",
    "otra/avatares/{bruno}/abc",
    "Avatares/{bruno}/abc",
    "",
])
def test_un_avatar_fuera_de_su_carpeta_es_ajeno(autorizado_organizador, organizador, db, nube,
                                                carpeta):
    ana = db.scalar(select(Usuario.id).where(Usuario.email == EMAIL_ADMIN))
    public_id = carpeta.format(ana=ana, bruno=organizador.id)
    r = guardar_avatar(autorizado_organizador, public_id, url_avatar(public_id or "x"))
    afirmar_error(r, "PUBLIC_ID_AJENO", 403)
    assert cuenta_en_la_base(db, organizador.id).avatar_public_id is None
    assert nube.pedidos == []


@sin_base
@pytest.mark.parametrize("url", [
    "https://res.cloudinary.com/otra-nube/image/upload/v1/{pid}.jpg",
    "https://res.cloudinary.com/nube-falsa/image/upload/c_fill,w_100/{pid}.jpg",
    "https://res.cloudinary.com/nube-falsa/image/upload/l_fetch:aHR0cHM6Ly9tYWxv/{pid}.jpg",
    "https://res.cloudinary.com/nube-falsa/video/upload/v1/{pid}.mp4",
    "https://res.cloudinary.com/nube-falsa/image/upload/v1/{pid}.gif",
    "https://res.cloudinary.com/nube-falsa/image/upload/v1/{pid}.svg",
    "https://res.cloudinary.com/nube-falsa/image/upload/v1/{otro}.jpg",
    "https://res.cloudinary.com/nube-falsa/image/upload/v1/{pid}.jpg?x=1",
    "http://res.cloudinary.com/nube-falsa/image/upload/v1/{pid}.jpg",
    "https://malo.test/nube-falsa/image/upload/v1/{pid}.jpg",
    "https://res.cloudinary.com/nube-falsa/image/upload/v1/{pid}/../../../otra/image/upload/x.jpg",
])
def test_un_avatar_con_una_url_que_no_es_la_suya(autorizado_organizador, organizador, db, url):
    public_id = f"avatares/{organizador.id}/abc"
    r = guardar_avatar(autorizado_organizador, public_id,
                       url.format(pid=public_id, otro=f"avatares/{organizador.id}/xyz"))
    afirmar_error(r, "ARCHIVO_INVALIDO", 400)
    assert cuenta_en_la_base(db, organizador.id).avatar_public_id is None


@sin_base
@pytest.mark.parametrize("cuerpo", [
    {}, {"public_id": "avatares/1/a"}, {"url": "https://x.test/a.jpg"},
    {"public_id": "a" * 201, "url": "https://x.test/a.jpg"},
    {"public_id": "avatares/1/a", "url": "h" * 501},
])
def test_guardar_el_avatar_con_datos_invalidos(autorizado_organizador, cuerpo):
    afirmar_error(autorizado_organizador.put("/api/admin/yo/avatar", json=cuerpo),
                  "DATOS_INVALIDOS", 422)


@sin_base
def test_reemplazar_el_avatar_borra_el_anterior(autorizado_organizador, organizador, nube):
    viejo, nuevo = f"avatares/{organizador.id}/viejo", f"avatares/{organizador.id}/nuevo"
    guardar_avatar(autorizado_organizador, viejo)
    r = guardar_avatar(autorizado_organizador, nuevo)
    assert r.json()["avatar_url"] == url_avatar(nuevo)

    assert nube.borrados() == [("imagen", viejo)]
    [pedido] = nube.pedidos
    assert pedido["url"] == f"https://api.cloudinary.com/v1_1/{NUBE}/resources/image/upload"
    assert pedido["auth"] == (CLAVE, SECRETO)
    assert pedido["params"]["invalidate"] == "true"


@sin_base
def test_guardar_el_mismo_avatar_no_borra_nada(autorizado_organizador, organizador, nube):
    public_id = f"avatares/{organizador.id}/uno"
    for _ in range(2):
        assert guardar_avatar(autorizado_organizador, public_id).status_code == 200
    assert nube.pedidos == []


@sin_base
def test_quitar_el_avatar(autorizado_organizador, organizador, nube, db):
    public_id = f"avatares/{organizador.id}/uno"
    guardar_avatar(autorizado_organizador, public_id)

    r = autorizado_organizador.post("/api/admin/yo/avatar/quitar")
    assert r.status_code == 200, r.text
    assert r.json()["avatar_url"] is None
    assert r.json() == autorizado_organizador.get("/api/admin/yo").json()
    cuenta = cuenta_en_la_base(db, organizador.id)
    assert (cuenta.avatar_public_id, cuenta.avatar_url) == (None, None)
    assert nube.borrados() == [("imagen", public_id)]

    # Idempotente: sin avatar no hace nada, ni pide otro borrado.
    assert autorizado_organizador.post("/api/admin/yo/avatar/quitar").status_code == 200
    assert len(nube.pedidos) == 1


@sin_base
@pytest.mark.parametrize("falla", [
    lambda: httpx.Response(500, text="error de Cloudinary"),
    lambda: httpx.ConnectError("sin red"),
])
def test_si_cloudinary_no_borra_el_anterior_igual_se_guarda(autorizado_organizador, organizador,
                                                            nube, caplog, falla):
    guardar_avatar(autorizado_organizador, f"avatares/{organizador.id}/viejo")
    nube.falla = falla
    with caplog.at_level(logging.INFO, logger=cs.log_avatares.name):
        r = guardar_avatar(autorizado_organizador, f"avatares/{organizador.id}/nuevo")
        assert autorizado_organizador.post("/api/admin/yo/avatar/quitar").status_code == 200
    assert r.status_code == 200
    errores = [x for x in caplog.records if x.name == cs.log_avatares.name]
    assert [x.levelno for x in errores] == [logging.ERROR, logging.ERROR]
    assert all(x.getMessage().startswith("avatares:") for x in errores)
    assert SECRETO not in caplog.text


@sin_base
def test_sin_credenciales_no_se_pide_ningun_borrado(autorizado_organizador, organizador, nube,
                                                    monkeypatch):
    guardar_avatar(autorizado_organizador, f"avatares/{organizador.id}/uno")
    monkeypatch.setattr(cs.config, "CLOUDINARY_API_SECRET", "")
    assert autorizado_organizador.post("/api/admin/yo/avatar/quitar").status_code == 200
    assert nube.pedidos == []


def test_el_borrado_del_anterior_no_sale_de_la_carpeta_de_la_cuenta(nube):
    """Aunque en la base hubiera quedado algo raro, nunca se pide borrar fuera
    de `avatares/{id}/` de esa cuenta."""
    for raro in ("eventos/ab12cd34/x", "avatares/2/x", "avatares/1/../2/x", "avatares/1/"):
        cs.borrar_avatar_anterior(raro, 1)
    assert nube.pedidos == []


@sin_base
def test_eliminar_una_cuenta_con_avatar_borra_su_carpeta(autorizado_organizador, organizador,
                                                         superadmin, cliente_con_base, nube, db):
    id_bruno = organizador.id
    guardar_avatar(autorizado_organizador, f"avatares/{id_bruno}/uno")
    r = cliente_con_base.request("DELETE", f"/api/admin/cuentas/{id_bruno}",
                                 json={"confirmar_email": EMAIL_ORGANIZADOR},
                                 headers=bearer_de(superadmin))
    assert r.status_code == 200, r.text
    assert nube.borrados() == [("prefijo", f"avatares/{id_bruno}/")], "con la barra final"
    assert nube.pedidos[0]["url"].endswith("/resources/image/upload")


@sin_base
def test_eliminar_una_cuenta_sin_avatar_no_pide_nada(cliente_con_base, organizador, superadmin,
                                                     nube):
    r = cliente_con_base.request("DELETE", f"/api/admin/cuentas/{organizador.id}",
                                 json={"confirmar_email": EMAIL_ORGANIZADOR},
                                 headers=bearer_de(superadmin))
    assert r.status_code == 200, r.text
    assert nube.pedidos == []


@sin_base
def test_eliminar_la_cuenta_aunque_cloudinary_falle(autorizado_organizador, organizador,
                                                    superadmin, cliente_con_base, nube, db, caplog):
    id_bruno = organizador.id
    guardar_avatar(autorizado_organizador, f"avatares/{id_bruno}/uno")
    nube.falla = lambda: httpx.ConnectError("sin red")
    with caplog.at_level(logging.INFO, logger=cs.log_avatares.name):
        r = cliente_con_base.request("DELETE", f"/api/admin/cuentas/{id_bruno}",
                                     json={"confirmar_email": EMAIL_ORGANIZADOR},
                                     headers=bearer_de(superadmin))
    assert r.status_code == 200, r.text
    db.expunge_all()
    assert db.get(Usuario, id_bruno) is None, "la cuenta igual se eliminó"
    errores = [x for x in caplog.records if x.name == cs.log_avatares.name]
    assert [x.levelno for x in errores] == [logging.ERROR]
    assert EMAIL_ORGANIZADOR not in caplog.text


# ─────────────────────────────────────────────────────────────
# Predeterminados al crear un evento
# ─────────────────────────────────────────────────────────────

MIS_PREDETERMINADOS = {
    "segundos_por_foto": 12,
    "max_fotos_por_dispositivo": 3,
    "pantalla": {"fondo": "negro", "transicion": "corte",
                 "mostrar_nombre": False, "mostrar_qr": False},
}
ESTILO_DE_MIS_PREDETERMINADOS = {
    "pantalla_fondo": "negro",
    "pantalla_transicion": "corte",
    "pantalla_mostrar_nombre": False,
    "pantalla_mostrar_qr": False,
}


def fecha_valida() -> str:
    return (hoy_en_argentina() + timedelta(days=10)).isoformat()


@sin_base
def test_un_evento_nuevo_nace_con_mis_predeterminados(autorizado_organizador):
    autorizado_organizador.patch("/api/admin/yo", json={"predeterminados": MIS_PREDETERMINADOS})
    r = autorizado_organizador.post("/api/admin/eventos",
                                    json={"nombre": "Cumple", "fecha_evento": fecha_valida()})
    assert r.status_code == 201, r.text
    evento = r.json()
    assert (evento["segundos_por_foto"], evento["max_fotos_por_dispositivo"]) == (12, 3)
    assert {k: evento[k] for k in ESTILO_POR_DEFECTO} == ESTILO_DE_MIS_PREDETERMINADOS


@sin_base
def test_sin_tocar_nada_un_evento_nace_como_siempre(autorizado_organizador):
    evento = autorizado_organizador.post(
        "/api/admin/eventos", json={"nombre": "Cumple", "fecha_evento": fecha_valida()}
    ).json()
    assert (evento["segundos_por_foto"], evento["max_fotos_por_dispositivo"]) == (7, 10)
    assert {k: evento[k] for k in ESTILO_POR_DEFECTO} == ESTILO_POR_DEFECTO


@sin_base
def test_un_admin_que_crea_para_otra_cuenta_usa_los_del_dueno(autorizado, autorizado_organizador,
                                                              organizador):
    """El evento es de la otra cuenta: nace con los predeterminados de ella, no
    con los del admin que lo crea. Y el del admin para sí, con los suyos."""
    autorizado_organizador.patch("/api/admin/yo", json={"predeterminados": MIS_PREDETERMINADOS})
    autorizado.patch("/api/admin/yo", json={"predeterminados": {
        "segundos_por_foto": 20, "max_fotos_por_dispositivo": 40,
        "pantalla": {"fondo": "desenfocado", "transicion": "fundido",
                     "mostrar_nombre": True, "mostrar_qr": True},
    }})

    para_bruno = autorizado.post("/api/admin/eventos", json={
        "nombre": "De Bruno", "fecha_evento": fecha_valida(), "organizador_id": organizador.id,
    }).json()
    assert para_bruno["organizador_id"] == organizador.id
    assert (para_bruno["segundos_por_foto"], para_bruno["max_fotos_por_dispositivo"]) == (12, 3)
    assert {k: para_bruno[k] for k in ESTILO_POR_DEFECTO} == ESTILO_DE_MIS_PREDETERMINADOS

    de_ana = autorizado.post("/api/admin/eventos",
                             json={"nombre": "De Ana", "fecha_evento": fecha_valida()}).json()
    assert (de_ana["segundos_por_foto"], de_ana["max_fotos_por_dispositivo"]) == (20, 40)
    assert {k: de_ana[k] for k in ESTILO_POR_DEFECTO} == ESTILO_POR_DEFECTO


@sin_base
def test_cambiar_los_predeterminados_no_toca_los_eventos_que_ya_existen(autorizado_organizador):
    viejo = autorizado_organizador.post(
        "/api/admin/eventos", json={"nombre": "Viejo", "fecha_evento": fecha_valida()}
    ).json()
    autorizado_organizador.patch("/api/admin/yo", json={"predeterminados": MIS_PREDETERMINADOS})
    [igual] = [e for e in autorizado_organizador.get("/api/admin/eventos").json()
               if e["id"] == viejo["id"]]
    assert igual == viejo


# ─────────────────────────────────────────────────────────────
# El estilo de la pantalla de un evento
# ─────────────────────────────────────────────────────────────

@sin_base
def test_el_evento_admin_trae_el_estilo(autorizado, eventos):
    for evento in autorizado.get("/api/admin/eventos").json():
        assert {k: evento[k] for k in ESTILO_POR_DEFECTO} == ESTILO_POR_DEFECTO


@sin_base
def test_cambiar_el_estilo_de_la_pantalla(autorizado, eventos, db):
    activo = eventos["activo"]
    r = autorizado.patch(f"/api/admin/eventos/{activo.id}", json={"pantalla_fondo": "negro"})
    assert r.status_code == 200, r.text
    assert {k: r.json()[k] for k in ESTILO_POR_DEFECTO} == {
        **ESTILO_POR_DEFECTO, "pantalla_fondo": "negro"}
    assert r.json()["segundos_por_foto"] == 7 and r.json()["estado"] == "activo"

    r = autorizado.patch(f"/api/admin/eventos/{activo.id}", json={
        "pantalla_transicion": "corte", "pantalla_mostrar_nombre": False,
        "pantalla_mostrar_qr": False,
    })
    assert {k: r.json()[k] for k in ESTILO_POR_DEFECTO} == ESTILO_DE_MIS_PREDETERMINADOS
    db.expunge_all()
    fila = db.get(Evento, activo.id)
    assert (fila.pantalla_fondo, fila.pantalla_transicion, fila.pantalla_mostrar_nombre,
            fila.pantalla_mostrar_qr) == ("negro", "corte", False, False)

    # Idempotente, y con un solo campo alcanza (también un false).
    otra = autorizado.patch(f"/api/admin/eventos/{activo.id}", json={"pantalla_mostrar_qr": False})
    assert otra.status_code == 200 and otra.json() == r.json()


@sin_base
@pytest.mark.parametrize("cuerpo", [
    {"pantalla_fondo": "blanco"},
    {"pantalla_transicion": "zoom"},
    {"pantalla_mostrar_nombre": "tal vez"},
    {"pantalla_mostrar_qr": None},
])
def test_estilo_de_pantalla_invalido(autorizado, eventos, cuerpo):
    afirmar_error(autorizado.patch(f"/api/admin/eventos/{eventos['activo'].id}", json=cuerpo),
                  "DATOS_INVALIDOS", 422)


@sin_base
def test_la_pantalla_toma_el_estilo_sin_recargar(cliente_con_base, autorizado, eventos):
    from tests.conftest import TOKEN_ACTIVO

    config = cliente_con_base.get(f"/api/pantalla/{TOKEN_ACTIVO}").json()["config"]
    assert {k: config[k] for k in ("fondo", "transicion", "mostrar_nombre", "mostrar_qr")} == {
        "fondo": "desenfocado", "transicion": "fundido", "mostrar_nombre": True, "mostrar_qr": True,
    }
    autorizado.patch(f"/api/admin/eventos/{eventos['activo'].id}", json={
        "pantalla_fondo": "negro", "pantalla_transicion": "corte",
        "pantalla_mostrar_nombre": False, "pantalla_mostrar_qr": False,
    })
    cuerpo = cliente_con_base.get(f"/api/pantalla/{TOKEN_ACTIVO}").json()
    assert {k: cuerpo["config"][k] for k in ("fondo", "transicion", "mostrar_nombre", "mostrar_qr")} == {
        "fondo": "negro", "transicion": "corte", "mostrar_nombre": False, "mostrar_qr": False,
    }
    assert "id" not in cuerpo["evento"] and "id" not in cuerpo["config"], "regla 1"


@sin_base
def test_la_pantalla_de_cada_evento_tiene_su_estilo(cliente_con_base, autorizado, eventos):
    from tests.conftest import TOKEN_ACTIVO, TOKEN_CERRADO

    autorizado.patch(f"/api/admin/eventos/{eventos['activo'].id}", json={"pantalla_fondo": "negro"})
    assert cliente_con_base.get(f"/api/pantalla/{TOKEN_ACTIVO}").json()["config"]["fondo"] == "negro"
    assert cliente_con_base.get(f"/api/pantalla/{TOKEN_CERRADO}").json()["config"]["fondo"] == (
        "desenfocado"), "aislamiento entre eventos"


@sin_base
def test_un_organizador_no_cambia_el_estilo_de_un_evento_ajeno(autorizado_organizador, eventos,
                                                               db):
    r = autorizado_organizador.patch(f"/api/admin/eventos/{eventos['activo'].id}",
                                     json={"pantalla_fondo": "negro"})
    afirmar_error(r, "EVENTO_NO_ENCONTRADO", 404)
    db.expunge_all()
    assert db.get(Evento, eventos["activo"].id).pantalla_fondo == "desenfocado"


@sin_base
def test_un_evento_creado_a_mano_nace_con_el_estilo_por_defecto(organizador, db):
    """Los DEFAULT de la base: un evento insertado sin decir nada (el seed, una
    migración) queda con la pantalla como se veía hasta ahora."""
    evento = nuevo_evento(db, organizador, "A mano", "am00an00")
    db.expunge_all()
    fila = db.get(Evento, evento.id)
    assert (fila.pantalla_fondo, fila.pantalla_transicion, fila.pantalla_mostrar_nombre,
            fila.pantalla_mostrar_qr) == ("desenfocado", "fundido", True, True)
    cuenta = db.get(Usuario, organizador.id)
    assert (cuenta.tema, cuenta.pred_segundos_por_foto, cuenta.sesiones_desde,
            cuenta.avatar_url) == ("automatico", 7, None, None)

