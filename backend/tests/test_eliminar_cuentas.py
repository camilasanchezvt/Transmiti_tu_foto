"""Eliminar una cuenta para siempre: DELETE /api/admin/cuentas/{id}.

Es la única excepción a la regla 7 ("nada se borra"), decidida por la usuaria
el 26-sep-2026, y es sólo para superadmins. La matriz, con actor = quien pide
y objetivo = la cuenta (sección 5 de CONSTRUIR-APP.md):

| objetivo                                  | organizador | admin | superadmin |
|-------------------------------------------|-------------|-------|------------|
| organizador (pendiente, activa o de baja) |     403     |  403  |    200     |
| admin (activo o de baja)                  |     403     |  403  |    200     |
| otro superadmin                           |     403     |  403  |    403     |
| la propia cuenta                          |     403     |  403  |    422     |
| una cuenta que no existe                  |     403     |  403  |    404     |

Y además `confirmar_email` tiene que ser el email de la cuenta, sin mayúsculas
ni espacios alrededor, o 422. En cada rechazo la base queda como estaba.

Qué pasa cuando se elimina: se borra sólo la fila de `usuarios`; sus eventos,
con fotos y videos, pasan al superadmin que la elimina; `fotos.moderada_por`
queda en NULL donde la nombraba. Todo en una transacción. El token de la cuenta
eliminada deja de servir y el email queda libre para registrarse de nuevo.

Las pruebas con base se saltean solas sin DATABASE_URL_TEST (el fixture
`motor_prueba` de conftest). Las del principio, sobre /docs y CORS, no la usan.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text, update

from app.config import obtener_config
from app.deps import es_superadmin, solo_superadmin
from app.errores import ErrorApp
from app.main import app
from app.models import Evento, Foto, Usuario
from app.routers import cuentas as rutas_cuentas
from app.routers.admin import hoy_en_argentina
from tests.conftest import (
    EMAIL_ADMIN,
    EMAIL_BAJA,
    EMAIL_ORGANIZADOR,
    EMAIL_PENDIENTE,
    EMAIL_SUPERADMIN,
    PASSWORD_ADMIN,
    PASSWORD_CUENTA,
    iniciar_sesion,
    nueva_cuenta,
)
from tests.test_cuentas import afirmar_error, bearer, con_fotos, login, nuevo_evento
from tests.test_superadmin import bearer_de

SIN_PERMISO = "No tenés permiso para esto"
A_UN_SUPERADMIN = "A una cuenta superadmin no se la elimina desde el panel"
LA_PROPIA = "No podés eliminar tu propia cuenta"
NO_COINCIDE = "El email no coincide con el de la cuenta"
NO_EXISTE = "No encontramos esa cuenta"
DATOS_INVALIDOS = "Los datos enviados no son válidos"

RUTA = "/api/admin/cuentas/{id}"


def eliminar(cliente, id_cuenta, confirmar_email, actor: Usuario | None = None):
    """DELETE con cuerpo JSON. httpx no acepta `json=` en `.delete()`, por eso `request`."""
    return cliente.request(
        "DELETE",
        RUTA.format(id=id_cuenta),
        json={"confirmar_email": confirmar_email},
        headers=bearer_de(actor) if actor is not None else None,
    )


# ─────────────────────────────────────────────────────────────
# Sin base: /docs, CORS y la dependencia
# ─────────────────────────────────────────────────────────────

def test_docs_publica_el_cuerpo_y_la_respuesta():
    """El email va en el cuerpo, nunca en la URL, y la respuesta es sólo un número."""
    esquema = TestClient(app).get("/openapi.json").json()
    operacion = esquema["paths"]["/api/admin/cuentas/{id_cuenta}"]["delete"]

    cuerpo = operacion["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    assert cuerpo == "#/components/schemas/PedidoEliminarCuenta"
    assert set(esquema["components"]["schemas"]["PedidoEliminarCuenta"]["properties"]) == {
        "confirmar_email"
    }
    assert [p["name"] for p in operacion["parameters"]] == ["id_cuenta"]

    ok = operacion["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    assert ok == "#/components/schemas/CuentaEliminada"
    assert set(esquema["components"]["schemas"]["CuentaEliminada"]["properties"]) == {
        "eventos_transferidos"
    }
    assert {"401", "403", "404", "422"} <= set(operacion["responses"])


def test_cors_deja_pasar_el_delete():
    """Sin DELETE en allow_methods, el navegador corta el pedido en el preflight."""
    origenes = obtener_config().origenes_cors
    if not origenes:
        pytest.skip("sin CORS_ORIGINS")
    r = TestClient(app).options(
        "/api/admin/cuentas/1",
        headers={
            "Origin": origenes[0],
            "Access-Control-Request-Method": "DELETE",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert r.status_code == 200, r.text
    assert "DELETE" in r.headers["access-control-allow-methods"]


def test_solo_superadmin_acepta_solo_al_superadmin():
    superadmin = Usuario(id=1, email="s@x.test", nombre="S", rol="superadmin", estado="activa")
    assert solo_superadmin(superadmin) is superadmin and es_superadmin(superadmin)
    for rol in ("admin", "organizador"):
        with pytest.raises(ErrorApp) as error:
            solo_superadmin(Usuario(id=2, email="a@x.test", nombre="A", rol=rol, estado="activa"))
        assert (error.value.http, error.value.codigo, error.value.mensaje) == (
            403, "NO_AUTORIZADO", SIN_PERMISO,
        )


# ─────────────────────────────────────────────────────────────
# Las cuentas y sus eventos
# ─────────────────────────────────────────────────────────────

@pytest.fixture()
def cuentas(limpiar, superadmin, organizador, cuenta_pendiente, cuenta_baja) -> dict[str, Usuario]:
    """Una cuenta por cada tipo de objetivo, como en test_superadmin.py. Ana, la
    de `limpiar`, es la `admin`; Sofía, la `superadmin`."""
    db = limpiar
    return {
        "superadmin": superadmin,
        "otro_superadmin": nueva_cuenta(db, "tomas@transmitifoto.test", "Tomás Superadmin",
                                        rol="superadmin"),
        "admin": db.scalar(select(Usuario).where(Usuario.email == EMAIL_ADMIN)),
        "otro_admin": nueva_cuenta(db, "gabi@transmitifoto.test", "Gabi Admin", rol="admin"),
        "admin_de_baja": nueva_cuenta(db, "hugo@transmitifoto.test", "Hugo Admin de Baja",
                                      rol="admin", estado="baja"),
        "organizador": organizador,
        "pendiente": cuenta_pendiente,
        "baja": cuenta_baja,
    }


MODERADA_EN = datetime(2026, 9, 12, 23, 30, tzinfo=timezone.utc)


def moderada_por(db, foto: Foto, cuenta: Usuario, estado: str) -> None:
    db.execute(
        update(Foto)
        .where(Foto.id == foto.id)
        .values(estado=estado, moderada_por=cuenta.id, moderada_en=MODERADA_EN)
    )
    db.commit()


@pytest.fixture()
def eventos(db, cuentas) -> dict[str, Evento]:
    """Bruno tiene dos eventos, uno abierto con su video listo y uno terminado;
    Ernesto (de baja) y Gabi (admin), uno cada uno; Ana, uno. Todos con fotos.

    Moderaron: Bruno, en su evento; Gabi, en el de Bruno y en el de Ana; Ana,
    en el suyo. Así se ve que eliminar a una cuenta pone en NULL sólo lo suyo.
    Cada evento de Bruno y de Ana queda con una pendiente, una aprobada y una
    rechazada (`con_fotos` trae dos pendientes y una aprobada).
    """
    de_bruno = nuevo_evento(db, cuentas["organizador"], "Cumple de Bruno", "br00no11")
    de_bruno.video_estado = "listo"
    de_bruno.video_public_id = "eventos/br00no11/video_1"
    de_bruno.video_url = "https://res.cloudinary.com/demo/video/upload/eventos/br00no11/video_1.mp4"
    de_bruno.video_fotos = 1
    db.commit()
    otro_de_bruno = nuevo_evento(db, cuentas["organizador"], "Bautismo de Bruno", "br00no22",
                                 estado="cerrado", fecha=date(2026, 9, 20))
    de_ernesto = nuevo_evento(db, cuentas["baja"], "Egresados de Ernesto", "er00ne11",
                              estado="cerrado", fecha=date(2026, 9, 5))
    de_gabi = nuevo_evento(db, cuentas["otro_admin"], "Aniversario de Gabi", "ga00bi11",
                           estado="borrador")
    de_ana = nuevo_evento(db, cuentas["admin"], "Casamiento de Ana", "an00aa11")

    fotos = {nombre: con_fotos(db, e) for nombre, e in (
        ("de_bruno", de_bruno), ("otro_de_bruno", otro_de_bruno), ("de_ernesto", de_ernesto),
        ("de_gabi", de_gabi), ("de_ana", de_ana),
    )}
    moderada_por(db, fotos["de_bruno"][2], cuentas["organizador"], "aprobada")
    moderada_por(db, fotos["de_bruno"][0], cuentas["otro_admin"], "rechazada")
    moderada_por(db, fotos["de_ana"][2], cuentas["otro_admin"], "aprobada")
    moderada_por(db, fotos["de_ana"][0], cuentas["admin"], "rechazada")
    return {"de_bruno": de_bruno, "otro_de_bruno": otro_de_bruno, "de_ernesto": de_ernesto,
            "de_gabi": de_gabi, "de_ana": de_ana}


def estado_de_la_base(db) -> dict[str, list]:
    """Todo lo que eliminar una cuenta podría tocar, fila por fila.

    Consultas de columnas y no de objetos: no pasan por el mapa de identidad de
    la sesión, así que ven siempre lo que está en la base. Donde hace falta un
    objeto fresco, las pruebas usan `expunge_all` y no `expire_all`: una cuenta
    eliminada que quedó vencida en la sesión levanta ObjectDeletedError."""
    def filas(consulta) -> list[dict]:
        return [dict(fila._mapping) for fila in db.execute(consulta)]

    return {
        "usuarios": filas(
            select(Usuario.id, Usuario.email, Usuario.nombre, Usuario.password_hash,
                   Usuario.rol, Usuario.estado, Usuario.creado_en).order_by(Usuario.id)
        ),
        "eventos": filas(
            select(Evento.id, Evento.usuario_id, Evento.nombre, Evento.estado,
                   Evento.codigo_publico, Evento.token_pantalla, Evento.video_estado,
                   Evento.video_url).order_by(Evento.id)
        ),
        "fotos": filas(
            select(Foto.id, Foto.evento_id, Foto.public_id, Foto.url, Foto.estado,
                   Foto.moderada_por, Foto.moderada_en).order_by(Foto.id)
        ),
    }


def ids_de_usuarios(estado: dict[str, list]) -> list[int]:
    return [fila["id"] for fila in estado["usuarios"]]


def existe(db, id_cuenta: int) -> bool:
    return db.scalar(select(Usuario.id).where(Usuario.id == id_cuenta)) is not None


# ─────────────────────────────────────────────────────────────
# La matriz: quién puede eliminar a quién
# ─────────────────────────────────────────────────────────────

OBJETIVOS = ["otro_superadmin", "superadmin", "admin", "otro_admin", "admin_de_baja",
             "organizador", "pendiente", "baja"]

# (actor, objetivo) → (HTTP, código, mensaje). Lo que no está es 200.
RECHAZOS = {
    ("superadmin", "otro_superadmin"): (403, "NO_AUTORIZADO", A_UN_SUPERADMIN),
    ("superadmin", "superadmin"): (422, "DATOS_INVALIDOS", LA_PROPIA),
    **{("admin", o): (403, "NO_AUTORIZADO", SIN_PERMISO) for o in OBJETIVOS},
    **{("organizador", o): (403, "NO_AUTORIZADO", SIN_PERMISO) for o in OBJETIVOS},
}

CASOS = [(a, o) for a in ("superadmin", "admin", "organizador") for o in OBJETIVOS]


@pytest.mark.parametrize("actor,objetivo", CASOS, ids=[f"{a}-{o}" for a, o in CASOS])
def test_matriz_de_eliminar_cuentas(cliente_con_base, cuentas, db, actor, objetivo):
    """Siempre con el email correcto de la cuenta: si se rechaza, es por el permiso."""
    cuenta = cuentas[objetivo]
    antes = estado_de_la_base(db)

    r = eliminar(cliente_con_base, cuenta.id, cuenta.email, actor=cuentas[actor])

    rechazo = RECHAZOS.get((actor, objetivo))
    if rechazo is None:
        assert r.status_code == 200, r.text
        assert r.json() == {"eventos_transferidos": 0}
        despues = estado_de_la_base(db)
        assert ids_de_usuarios(despues) == [i for i in ids_de_usuarios(antes) if i != cuenta.id], (
            "se fue esa fila y ninguna otra"
        )
        assert not existe(db, cuenta.id)
        return
    http, codigo, mensaje = rechazo
    afirmar_error(r, codigo, http)
    assert r.json()["error"]["mensaje"] == mensaje
    assert estado_de_la_base(db) == antes, "y la base quedó como estaba"


def test_sin_sesion_o_con_un_token_que_no_sirve_es_401(cliente_con_base, cuentas, db):
    bruno = cuentas["organizador"]
    antes = estado_de_la_base(db)
    for cabeceras in (None, bearer("no-es-un-token")):
        r = cliente_con_base.request("DELETE", RUTA.format(id=bruno.id), headers=cabeceras,
                                     json={"confirmar_email": bruno.email})
        afirmar_error(r, "NO_AUTORIZADO", 401)
    assert estado_de_la_base(db) == antes


def test_cuenta_inexistente(cliente_con_base, cuentas, db):
    antes = estado_de_la_base(db)
    r = eliminar(cliente_con_base, 999999, "nadie@transmitifoto.test", actor=cuentas["superadmin"])
    afirmar_error(r, "DATOS_INVALIDOS", 404)
    assert r.json()["error"]["mensaje"] == NO_EXISTE
    assert estado_de_la_base(db) == antes


def test_un_id_que_no_entra_en_bigint(cliente_con_base, cuentas, db):
    antes = estado_de_la_base(db)
    r = eliminar(cliente_con_base, 10**20, "x@transmitifoto.test", actor=cuentas["superadmin"])
    afirmar_error(r, "DATOS_INVALIDOS", 422)
    assert estado_de_la_base(db) == antes


def test_eliminar_dos_veces_la_segunda_es_404(cliente_con_base, cuentas, db):
    bruno, sofia = cuentas["organizador"], cuentas["superadmin"]
    assert eliminar(cliente_con_base, bruno.id, bruno.email, actor=sofia).status_code == 200
    antes = estado_de_la_base(db)
    r = eliminar(cliente_con_base, bruno.id, bruno.email, actor=sofia)
    afirmar_error(r, "DATOS_INVALIDOS", 404)
    assert r.json()["error"]["mensaje"] == NO_EXISTE
    assert estado_de_la_base(db) == antes


# ─────────────────────────────────────────────────────────────
# Qué se mira primero
# ─────────────────────────────────────────────────────────────

def test_el_permiso_va_antes_que_el_email(cliente_con_base, cuentas, db):
    """Un admin con el email correcto: 403. Un superadmin sobre otro superadmin
    con el email mal: 403, no "no coincide". Sobre la propia con el email mal:
    "tu propia cuenta". Una que no existe: 404 con cualquier email."""
    sofia = cuentas["superadmin"]
    antes = estado_de_la_base(db)

    r = eliminar(cliente_con_base, cuentas["organizador"].id, EMAIL_ORGANIZADOR,
                 actor=cuentas["admin"])
    afirmar_error(r, "NO_AUTORIZADO", 403)

    r = eliminar(cliente_con_base, cuentas["otro_superadmin"].id, "otro@x.test", actor=sofia)
    afirmar_error(r, "NO_AUTORIZADO", 403)
    assert r.json()["error"]["mensaje"] == A_UN_SUPERADMIN

    r = eliminar(cliente_con_base, sofia.id, "otro@x.test", actor=sofia)
    afirmar_error(r, "DATOS_INVALIDOS", 422)
    assert r.json()["error"]["mensaje"] == LA_PROPIA

    r = eliminar(cliente_con_base, 999999, EMAIL_ORGANIZADOR, actor=sofia)
    afirmar_error(r, "DATOS_INVALIDOS", 404)

    assert estado_de_la_base(db) == antes


def test_un_admin_sin_cuerpo_recibe_403_y_no_422(cliente_con_base, cuentas):
    """El permiso se decide antes de mirar el cuerpo: a quien no es superadmin no
    se le dice qué le falta al pedido."""
    for actor in ("admin", "organizador"):
        r = cliente_con_base.request("DELETE", RUTA.format(id=cuentas["pendiente"].id),
                                     headers=bearer_de(cuentas[actor]))
        afirmar_error(r, "NO_AUTORIZADO", 403)


# ─────────────────────────────────────────────────────────────
# La confirmación por email, del lado del servidor
# ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("escrito", [
    EMAIL_ORGANIZADOR,
    EMAIL_ORGANIZADOR.upper(),
    "Bruno@TransmitiFoto.Test",
    f"  {EMAIL_ORGANIZADOR}  ",
    f"\t{EMAIL_ORGANIZADOR.upper()}\n",
], ids=["igual", "mayusculas", "mezcla", "espacios", "tab-y-enter"])
def test_el_email_se_compara_sin_mayusculas_ni_espacios_alrededor(cliente_con_base, cuentas,
                                                                  db, escrito):
    bruno = cuentas["organizador"]
    r = eliminar(cliente_con_base, bruno.id, escrito, actor=cuentas["superadmin"])
    assert r.status_code == 200, r.text
    assert not existe(db, bruno.id)


@pytest.mark.parametrize("escrito", [
    "",
    "   ",
    EMAIL_PENDIENTE,
    EMAIL_SUPERADMIN,
    "bruno@transmitifoto.tes",
    "bruno@transmitifoto.test.",
    "bruno @transmitifoto.test",
    "bruno",
    "Bruno Organizador",
], ids=["vacio", "solo-espacios", "el-de-otra-cuenta", "el-propio", "le-falta-una-letra",
        "le-sobra-un-punto", "espacio-en-el-medio", "sin-dominio", "el-nombre"])
def test_si_el_email_no_coincide_no_se_elimina(cliente_con_base, cuentas, db, escrito):
    bruno = cuentas["organizador"]
    antes = estado_de_la_base(db)
    r = eliminar(cliente_con_base, bruno.id, escrito, actor=cuentas["superadmin"])
    afirmar_error(r, "DATOS_INVALIDOS", 422)
    assert r.json()["error"]["mensaje"] == NO_COINCIDE
    assert estado_de_la_base(db) == antes


@pytest.mark.parametrize("cuerpo", [
    None,
    {},
    {"confirmar_email": None},
    {"confirmar_email": 123},
    {"email": EMAIL_ORGANIZADOR},
    {"confirmar_email": "b" * 250 + "@x.test"},
], ids=["sin-cuerpo", "vacio", "nulo", "numero", "otro-campo", "demasiado-largo"])
def test_un_cuerpo_mal_formado_es_datos_invalidos(cliente_con_base, cuentas, db, cuerpo):
    bruno = cuentas["organizador"]
    antes = estado_de_la_base(db)
    extra = {} if cuerpo is None else {"json": cuerpo}
    r = cliente_con_base.request("DELETE", RUTA.format(id=bruno.id),
                                 headers=bearer_de(cuentas["superadmin"]), **extra)
    afirmar_error(r, "DATOS_INVALIDOS", 422)
    assert r.json()["error"]["mensaje"] == DATOS_INVALIDOS
    assert estado_de_la_base(db) == antes


# ─────────────────────────────────────────────────────────────
# Qué pasa con los eventos, las fotos y lo que moderó
# ─────────────────────────────────────────────────────────────

def test_sus_eventos_pasan_al_superadmin_con_fotos_y_video(cliente_con_base, cuentas, eventos,
                                                           db):
    bruno, sofia, ana = cuentas["organizador"], cuentas["superadmin"], cuentas["admin"]
    antes = estado_de_la_base(db)

    r = eliminar(cliente_con_base, bruno.id, bruno.email, actor=sofia)
    assert r.status_code == 200, r.text
    assert r.json() == {"eventos_transferidos": 2}

    despues = estado_de_la_base(db)
    de_bruno = {eventos["de_bruno"].id, eventos["otro_de_bruno"].id}
    # Los eventos: los mismos, iguales en todo salvo el dueño de los de Bruno.
    esperados = [
        {**fila, "usuario_id": sofia.id} if fila["id"] in de_bruno else fila
        for fila in antes["eventos"]
    ]
    assert despues["eventos"] == esperados
    # Las fotos: todas siguen; sólo lo que moderó Bruno queda sin moderador.
    esperadas = [
        {**fila, "moderada_por": None} if fila["moderada_por"] == bruno.id else fila
        for fila in antes["fotos"]
    ]
    assert despues["fotos"] == esperadas
    assert [f["moderada_por"] for f in despues["fotos"]].count(None) == (
        [f["moderada_por"] for f in antes["fotos"]].count(None) + 1
    ), "la foto que moderó Bruno"
    # Las cuentas: se fue Bruno y nadie más.
    assert despues["usuarios"] == [u for u in antes["usuarios"] if u["id"] != bruno.id]

    # El evento de Ana y lo que moderaron Ana y Gabi, intactos.
    db.expunge_all()
    assert db.get(Evento, eventos["de_ana"].id).usuario_id == ana.id


def test_el_superadmin_los_ve_como_suyos_en_el_panel(cliente_con_base, cuentas, eventos, db):
    bruno, sofia = cuentas["organizador"], cuentas["superadmin"]
    como_sofia = bearer_de(sofia)
    eliminar(cliente_con_base, bruno.id, bruno.email, actor=sofia)

    r = cliente_con_base.get(f"/api/admin/eventos?organizador={sofia.id}", headers=como_sofia)
    filas = {e["nombre"]: e for e in r.json()}
    assert set(filas) == {"Cumple de Bruno", "Bautismo de Bruno"}
    for fila in filas.values():
        assert (fila["organizador_id"], fila["organizador_nombre"]) == (sofia.id,
                                                                        "Sofía Superadmin")
    assert filas["Cumple de Bruno"]["video_url_listo"] == eventos["de_bruno"].video_url
    cumple = filas["Cumple de Bruno"]
    assert (cumple["pendientes"], cumple["aprobadas"], cumple["rechazadas"]) == (1, 1, 1)

    r = cliente_con_base.get(f"/api/admin/eventos/{eventos['de_bruno'].id}/fotos",
                             headers=como_sofia)
    assert r.status_code == 200 and len(r.json()["fotos"]) == 3

    cuentas_del_panel = {c["email"]: c for c in
                         cliente_con_base.get("/api/admin/cuentas", headers=como_sofia).json()}
    assert EMAIL_ORGANIZADOR not in cuentas_del_panel
    assert cuentas_del_panel[EMAIL_SUPERADMIN]["eventos"] == 2
    assert cuentas_del_panel[EMAIL_SUPERADMIN]["ultimo_evento"] == str(
        eventos["de_bruno"].fecha_evento
    )


def test_los_invitados_y_la_pantalla_no_se_enteran(cliente_con_base, cuentas, eventos):
    """El evento abierto de Bruno sigue recibiendo fotos y la pantalla sigue andando:
    cambia el dueño, no las claves públicas."""
    evento = eventos["de_bruno"]
    eliminar(cliente_con_base, cuentas["organizador"].id, EMAIL_ORGANIZADOR,
             actor=cuentas["superadmin"])

    r = cliente_con_base.get(f"/api/e/{evento.codigo_publico}")
    assert r.status_code == 200 and r.json()["estado"] == "activo"
    r = cliente_con_base.get(f"/api/pantalla/{evento.token_pantalla}/fotos?desde=0")
    assert r.status_code == 200 and len(r.json()["fotos"]) == 1, "la aprobada"


@pytest.mark.parametrize("objetivo,cantidad", [("baja", 1), ("otro_admin", 1), ("pendiente", 0)])
def test_la_respuesta_dice_cuantos_eventos_pasaron(cliente_con_base, cuentas, eventos, db,
                                                  objetivo, cantidad):
    cuenta, sofia = cuentas[objetivo], cuentas["superadmin"]
    suyos = list(db.scalars(select(Evento.id).where(Evento.usuario_id == cuenta.id)))
    assert len(suyos) == cantidad

    r = eliminar(cliente_con_base, cuenta.id, cuenta.email, actor=sofia)
    assert r.json() == {"eventos_transferidos": cantidad}
    db.expunge_all()
    assert [db.get(Evento, i).usuario_id for i in suyos] == [sofia.id] * cantidad


def test_lo_que_moderaba_un_admin_eliminado_queda_sin_moderador(cliente_con_base, cuentas,
                                                               eventos, db):
    """Gabi moderó en el evento de Bruno y en el de Ana: esas dos fotos quedan
    con moderada_por en NULL, pero con su estado y su moderada_en. Lo de Ana y lo
    de Bruno sigue con su nombre."""
    gabi, ana, bruno = cuentas["otro_admin"], cuentas["admin"], cuentas["organizador"]

    def moderadas(cuenta: Usuario) -> dict[int, tuple]:
        db.expunge_all()
        return {
            f.id: (f.estado, f.moderada_en)
            for f in db.scalars(select(Foto).where(Foto.moderada_por == cuenta.id))
        }

    de_gabi = moderadas(gabi)
    de_ana, de_bruno = moderadas(ana), moderadas(bruno)
    assert {e for e, _ in de_gabi.values()} == {"aprobada", "rechazada"}
    assert len(de_ana) == len(de_bruno) == 1

    r = eliminar(cliente_con_base, gabi.id, gabi.email, actor=cuentas["superadmin"])
    assert r.status_code == 200, r.text

    db.expunge_all()
    for id_foto, (estado, moderada_en) in de_gabi.items():
        foto = db.get(Foto, id_foto)
        assert (foto.moderada_por, foto.estado, foto.moderada_en) == (None, estado, moderada_en)
    assert (moderadas(ana), moderadas(bruno)) == (de_ana, de_bruno)


def test_moderar_de_verdad_y_despues_eliminar(cliente_con_base, cuentas, eventos, db):
    """Lo mismo por el camino real: Gabi modera desde el panel y después la eliminan."""
    gabi = cuentas["otro_admin"]
    pendientes = list(db.scalars(
        select(Foto.id).where(Foto.evento_id == eventos["de_ana"].id,
                              Foto.estado == "pendiente")
    ))
    r = cliente_con_base.post("/api/admin/fotos/lote", headers=bearer_de(gabi),
                              json={"ids": pendientes, "estado": "rechazada"})
    assert r.json() == {"afectadas": len(pendientes)}

    eliminar(cliente_con_base, gabi.id, gabi.email, actor=cuentas["superadmin"])

    db.expunge_all()
    fotos = [db.get(Foto, i) for i in pendientes]
    assert {(f.estado, f.moderada_por) for f in fotos} == {("rechazada", None)}
    assert all(f.moderada_en is not None for f in fotos), "cuándo se moderó, sí queda"


def test_todo_en_una_transaccion(cliente_con_base, cuentas, eventos, db, monkeypatch):
    """Si el DELETE falla después de mover los eventos y de soltar lo moderado,
    no queda nada a medias: ni los eventos cambian de dueño ni las fotos pierden
    su moderador."""

    class DeleteQueFalla:
        def __init__(self, *_args) -> None:
            pass

        def where(self, *_args):
            return text("SELECT 1 / 0")

    monkeypatch.setattr(rutas_cuentas, "delete", DeleteQueFalla)
    bruno = cuentas["organizador"]
    antes = estado_de_la_base(db)

    r = eliminar(cliente_con_base, bruno.id, bruno.email, actor=cuentas["superadmin"])
    assert r.status_code >= 400
    assert estado_de_la_base(db) == antes


# ─────────────────────────────────────────────────────────────
# Después: el token no sirve y el email queda libre
# ─────────────────────────────────────────────────────────────

def test_el_token_de_la_cuenta_eliminada_deja_de_servir(cliente_con_base, cuentas, eventos):
    token = iniciar_sesion(cliente_con_base, EMAIL_ORGANIZADOR, PASSWORD_CUENTA)
    como_bruno = bearer(token)
    assert cliente_con_base.get("/api/admin/yo", headers=como_bruno).status_code == 200

    eliminar(cliente_con_base, cuentas["organizador"].id, EMAIL_ORGANIZADOR,
             actor=cuentas["superadmin"])

    for ruta in ("/api/admin/yo", "/api/admin/eventos",
                 f"/api/admin/eventos/{eventos['de_bruno'].id}/fotos"):
        afirmar_error(cliente_con_base.get(ruta, headers=como_bruno), "NO_AUTORIZADO", 401)

    # Y el login responde lo mismo que para un email que nunca existió.
    eliminada = login(cliente_con_base, EMAIL_ORGANIZADOR, PASSWORD_CUENTA)
    nunca = login(cliente_con_base, "nunca@transmitifoto.test", PASSWORD_CUENTA)
    afirmar_error(eliminada, "NO_AUTORIZADO", 401)
    assert eliminada.json() == nunca.json()


def test_el_email_queda_libre_para_registrarse_de_nuevo(cliente_con_base, cuentas, eventos, db):
    """La cuenta nueva es otra: otro id, pendiente, sin los eventos viejos. El
    token de la eliminada no le sirve ni cuando la nueva está activa, porque el
    id es IDENTITY y no se reusa."""
    bruno, sofia = cuentas["organizador"], cuentas["superadmin"]
    token_viejo = iniciar_sesion(cliente_con_base, EMAIL_ORGANIZADOR, PASSWORD_CUENTA)
    eliminar(cliente_con_base, bruno.id, bruno.email, actor=sofia)

    r = cliente_con_base.post("/api/cuentas/registro", json={
        "email": "Bruno@TransmitiFoto.test", "nombre": "Bruno de Nuevo",
        "password": "otra-clave-nueva",
    })
    assert r.status_code == 201 and r.json() == {"estado": "pendiente"}

    db.expunge_all()
    nueva = db.scalar(select(Usuario).where(Usuario.email == EMAIL_ORGANIZADOR))
    assert nueva is not None and nueva.id != bruno.id
    assert (nueva.nombre, nueva.rol, nueva.estado) == ("Bruno de Nuevo", "organizador",
                                                       "pendiente")

    r = cliente_con_base.patch(f"/api/admin/cuentas/{nueva.id}", json={"estado": "activa"},
                               headers=bearer_de(sofia))
    assert r.status_code == 200 and r.json()["eventos"] == 0

    afirmar_error(cliente_con_base.get("/api/admin/yo", headers=bearer(token_viejo)),
                  "NO_AUTORIZADO", 401)
    assert login(cliente_con_base, EMAIL_ORGANIZADOR, PASSWORD_CUENTA).status_code == 401, (
        "la contraseña vieja no sirve"
    )
    token_nuevo = iniciar_sesion(cliente_con_base, EMAIL_ORGANIZADOR, "otra-clave-nueva")
    r = cliente_con_base.get("/api/admin/eventos", headers=bearer(token_nuevo))
    assert r.status_code == 200 and r.json() == [], "los eventos viejos siguen con Sofía"


def test_eliminar_una_cuenta_de_baja_con_eventos(cliente_con_base, cuentas, eventos, db):
    """La baja se puede eliminar igual, y su login sigue sin servir (ahora como inexistente)."""
    ernesto = cuentas["baja"]
    assert login(cliente_con_base, EMAIL_BAJA, PASSWORD_CUENTA).status_code == 403
    r = eliminar(cliente_con_base, ernesto.id, EMAIL_BAJA, actor=cuentas["superadmin"])
    assert r.json() == {"eventos_transferidos": 1}
    assert login(cliente_con_base, EMAIL_BAJA, PASSWORD_CUENTA).status_code == 401


# ─────────────────────────────────────────────────────────────
# El log: ids, nunca emails
# ─────────────────────────────────────────────────────────────

def test_el_log_lleva_los_ids_y_no_los_emails(cliente_con_base, cuentas, eventos, caplog):
    bruno, sofia = cuentas["organizador"], cuentas["superadmin"]
    with caplog.at_level(logging.INFO, logger=rutas_cuentas.log.name):
        eliminar(cliente_con_base, bruno.id, bruno.email, actor=sofia)

    mensajes = [r.getMessage() for r in caplog.records if r.name == rutas_cuentas.log.name]
    assert len(mensajes) == 1, mensajes
    mensaje = mensajes[0]
    assert mensaje.startswith("cuentas:")
    assert f"cuenta {sofia.id}" in mensaje and f"cuenta {bruno.id}" in mensaje
    assert "2 eventos" in mensaje
    for dato in (EMAIL_ORGANIZADOR, EMAIL_SUPERADMIN, "Bruno", "Sofía", "@"):
        assert dato not in caplog.text


def test_un_rechazo_no_deja_linea_en_el_log(cliente_con_base, cuentas, caplog):
    with caplog.at_level(logging.INFO, logger=rutas_cuentas.log.name):
        eliminar(cliente_con_base, cuentas["organizador"].id, "otro@x.test",
                 actor=cuentas["superadmin"])
        eliminar(cliente_con_base, cuentas["organizador"].id, EMAIL_ORGANIZADOR,
                 actor=cuentas["admin"])
    assert [r for r in caplog.records if r.name == rutas_cuentas.log.name] == []


# ─────────────────────────────────────────────────────────────
# Con un login de verdad, de punta a punta
# ─────────────────────────────────────────────────────────────

def test_de_punta_a_punta_con_login(autorizado, autorizado_superadmin, cuentas, eventos, db):
    """Ana (admin) no puede; Sofía (superadmin) sí, con los tokens del login."""
    bruno = cuentas["organizador"]
    r = autorizado.request("DELETE", RUTA.format(id=bruno.id),
                           json={"confirmar_email": EMAIL_ORGANIZADOR})
    afirmar_error(r, "NO_AUTORIZADO", 403)

    r = autorizado_superadmin.request("DELETE", RUTA.format(id=bruno.id),
                                      json={"confirmar_email": EMAIL_ORGANIZADOR})
    assert r.status_code == 200 and r.json() == {"eventos_transferidos": 2}

    # Ana, admin, sigue viendo los eventos: ahora son de Sofía.
    filas = {e["nombre"]: e for e in autorizado.get("/api/admin/eventos").json()}
    assert filas["Cumple de Bruno"]["organizador_nombre"] == "Sofía Superadmin"
    assert login(autorizado, EMAIL_ADMIN, PASSWORD_ADMIN).status_code == 200


def test_los_eventos_transferidos_se_siguen_rigiendo_por_su_fecha(cliente_con_base, cuentas,
                                                                  eventos):
    """Cambia el dueño, no la fecha: vigentes e historial quedan donde estaban."""
    sofia = cuentas["superadmin"]
    eliminar(cliente_con_base, cuentas["organizador"].id, EMAIL_ORGANIZADOR, actor=sofia)
    consulta = f"/api/admin/eventos?organizador={sofia.id}&alcance="
    vigentes = [e["nombre"] for e in
                cliente_con_base.get(consulta + "vigentes", headers=bearer_de(sofia)).json()]
    historial = [e["nombre"] for e in
                 cliente_con_base.get(consulta + "historial", headers=bearer_de(sofia)).json()]
    assert vigentes == ["Cumple de Bruno"]
    assert historial == ["Bautismo de Bruno"]
    assert eventos["de_bruno"].fecha_evento == hoy_en_argentina() + timedelta(days=7)
