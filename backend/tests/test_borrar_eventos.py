"""Borrar un evento del Historial: DELETE /api/admin/eventos/{id}.

Es la segunda excepción a la regla 7 ("nada se borra"), junto con eliminar una
cuenta, decidida por la usuaria el 27-sep-2026. Las reglas (sección 5 de
CONSTRUIR-APP.md):

- Pueden un admin y un superadmin, sobre eventos de cualquier cuenta. Un
  organizador → 403, aunque el evento sea suyo y aunque falte el cuerpo.
- Sólo eventos del Historial, con el mismo criterio que `alcance=historial`:
  terminados de cualquier fecha, o sin publicar de fecha pasada. Uno abierto
  (de cualquier fecha) o uno sin publicar de hoy en adelante → 422.
- `confirmar_nombre` tiene que ser el nombre del evento como se ve en pantalla
  (sin mayúsculas, sin espacios alrededor, los de adentro juntados en uno y las
  tildes en NFC), y no vacío, o 422. Un evento inexistente → 404.
- Si Cloudinary está armando su video (y todavía no terminó), 422: el MP4
  aparecería en la carpeta después del borrado, para siempre.
- Se va TODO lo del evento: las filas de sus fotos, la del evento y, si
  todavía estaban, sus archivos de Cloudinary (imágenes y videos, con el
  prefijo exacto `eventos/{codigo}/` y la barra final). Si Cloudinary falla,
  503 y la base queda como estaba.
- En cada rechazo no se toca nada: ni la base ni Cloudinary.

Cloudinary está SIEMPRE simulado: un fixture automático reemplaza httpx.delete
por uno que falla si alguna prueba lo llama sin haber puesto su nube falsa.

"Hoy" es el 26/9/2026 para el panel (`routers.admin.hoy_en_argentina`, el del
listado) y para la limpieza (conftest): la corrida no depende del día.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import Counter
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import sessionmaker

from app import cloudinary_service as cs
from app import limpieza, vinculacion
from app.config import obtener_config
from app.main import app
from app.models import Base, Evento, Foto, Usuario
from app.routers import admin as rutas_admin
from tests.conftest import (
    EMAIL_ADMIN,
    EMAIL_ORGANIZADOR,
    EMAIL_SUPERADMIN,
    HOY_DEL_BORRADO,
    nueva_cuenta,
    url_de,
)
from tests.test_cuentas import afirmar_error
from tests.test_limpieza import CLAVE, NUBE, SECRETO, NubeFalsa
from tests.test_superadmin import bearer_de

HOY = HOY_DEL_BORRADO  # sábado 26/9/2026

SIN_PERMISO = "No tenés permiso para esto"
SOLO_DEL_HISTORIAL = (
    "Sólo se pueden borrar eventos del Historial. Si sigue abierto, terminalo primero."
)
NO_COINCIDE = "El nombre no coincide con el del evento"
NO_EXISTE = "No encontramos este evento"
NO_SE_BORRARON = "No pudimos borrar las fotos. Probá de nuevo en un rato."
VIDEO_EN_CURSO = "Se está armando el video de este evento. Probá de nuevo en unos minutos."
DATOS_INVALIDOS = "Los datos enviados no son válidos"

RUTA = "/api/admin/eventos/{id}"


@pytest.fixture(autouse=True)
def _hoy_del_panel(monkeypatch):
    """El "hoy" del listado es el de `routers.admin`: el Historial y el borrado
    lo leen del mismo lado, así que se fija ahí."""
    monkeypatch.setattr(rutas_admin, "hoy_en_argentina", lambda: HOY)


def _prohibido(*_a, **_k):
    raise AssertionError("una prueba intentó borrar en Cloudinary sin nube falsa")


def _video_prohibido(*_a, **_k):
    raise AssertionError("una prueba le pidió o consultó un video a Cloudinary sin simularlo")


@pytest.fixture(autouse=True)
def _cloudinary_simulado(monkeypatch):
    """Credenciales de mentira y ningún DELETE de verdad. Una prueba que no pide
    `nube` y aun así llama a Cloudinary falla: así se prueba que NO se llamó."""
    monkeypatch.setattr(httpx, "delete", _prohibido)
    monkeypatch.setattr(rutas_admin, "consultar_video", _video_prohibido)
    monkeypatch.setattr(rutas_admin, "pedir_video", _video_prohibido)
    monkeypatch.setattr(cs.config, "CLOUDINARY_CLOUD_NAME", NUBE)
    monkeypatch.setattr(cs.config, "CLOUDINARY_API_KEY", CLAVE)
    monkeypatch.setattr(cs.config, "CLOUDINARY_API_SECRET", SECRETO)


@pytest.fixture(autouse=True)
def _vinculaciones_limpias():
    vinculacion.reiniciar()
    yield
    vinculacion.reiniciar()


@pytest.fixture()
def nube(monkeypatch) -> NubeFalsa:
    falsa = NubeFalsa()
    monkeypatch.setattr(httpx, "delete", falsa.delete)
    return falsa


def borrar(cliente, id_evento, confirmar_nombre, actor: Usuario | None = None):
    """DELETE con cuerpo JSON. httpx no acepta `json=` en `.delete()`, por eso `request`."""
    return cliente.request(
        "DELETE",
        RUTA.format(id=id_evento),
        json={"confirmar_nombre": confirmar_nombre},
        headers=bearer_de(actor) if actor is not None else None,
    )


def mensaje_de_error(respuesta, codigo: str, http: int) -> str:
    afirmar_error(respuesta, codigo, http)
    return respuesta.json()["error"]["mensaje"]


# ─────────────────────────────────────────────────────────────
# Sin base: /docs y CORS
# ─────────────────────────────────────────────────────────────

def test_docs_publica_el_cuerpo_y_la_respuesta():
    """El nombre va en el cuerpo, y la respuesta es sólo la confirmación y un número."""
    esquema = TestClient(app).get("/openapi.json").json()
    operacion = esquema["paths"]["/api/admin/eventos/{id_evento}"]["delete"]

    cuerpo = operacion["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    assert cuerpo == "#/components/schemas/PedidoBorrarEvento"
    assert operacion["requestBody"]["required"] is True
    assert set(esquema["components"]["schemas"]["PedidoBorrarEvento"]["properties"]) == {
        "confirmar_nombre"
    }
    assert [p["name"] for p in operacion["parameters"]] == ["id_evento"]

    ok = operacion["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    assert ok == "#/components/schemas/EventoBorrado"
    assert set(esquema["components"]["schemas"]["EventoBorrado"]["properties"]) == {
        "eliminado", "fotos",
    }
    assert {"401", "403", "404", "422", "503"} <= set(operacion["responses"])


def test_cors_deja_pasar_el_delete_de_un_evento():
    origenes = obtener_config().origenes_cors
    if not origenes:
        pytest.skip("sin CORS_ORIGINS")
    r = TestClient(app).options(
        "/api/admin/eventos/1",
        headers={
            "Origin": origenes[0],
            "Access-Control-Request-Method": "DELETE",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert r.status_code == 200, r.text
    assert "DELETE" in r.headers["access-control-allow-methods"]


# ─────────────────────────────────────────────────────────────
# Cuentas, eventos y el estado completo de la base
# ─────────────────────────────────────────────────────────────

@pytest.fixture()
def cuentas(limpiar, superadmin, organizador, otro_organizador) -> dict[str, Usuario]:
    """Ana, la de `limpiar`, es la `admin`; Sofía, la `superadmin`."""
    db = limpiar
    return {
        "superadmin": superadmin,
        "admin": db.scalar(select(Usuario).where(Usuario.email == EMAIL_ADMIN)),
        "otro_admin": nueva_cuenta(db, "gabi@transmitifoto.test", "Gabi Admin", rol="admin"),
        "organizador": organizador,
        "otro_organizador": otro_organizador,
    }


_ESTADOS_FOTO = ["aprobada", "pendiente", "rechazada"]


def nuevo_evento(db, dueno: Usuario, nombre: str, codigo: str, *, estado: str = "cerrado",
                 fecha: date | None = None, fotos: int = 3, **extra) -> Evento:
    """Un evento con `fotos` filas de fotos (aprobada, pendiente, rechazada…),
    todas dentro de `eventos/{codigo}/`. Por defecto, terminado hace cinco días."""
    evento = Evento(
        usuario_id=dueno.id,
        nombre=nombre,
        fecha_evento=fecha or HOY - timedelta(days=5),
        codigo_publico=codigo,
        token_pantalla=f"T{codigo}".ljust(32, "x"),
        estado=estado,
        cerrado_en=datetime(2026, 9, 22, 3, 0, tzinfo=timezone.utc) if estado == "cerrado" else None,
        **extra,
    )
    db.add(evento)
    db.commit()
    for i in range(fotos):
        public_id = f"eventos/{codigo}/f{i:02d}"
        db.add(Foto(evento_id=evento.id, public_id=public_id, url=url_de(public_id),
                    ancho=1600, alto=1200, bytes=100000 + i, estado=_ESTADOS_FOTO[i % 3],
                    dispositivo_hash="d" * 32, nombre_invitado=f"Invitado {i}"))
    db.commit()
    return evento


@pytest.fixture()
def eventos(db, cuentas) -> dict[str, Evento]:
    """Eventos del Historial de cada tipo de cuenta, más dos que no lo son.

    - malena: de Bruno (organizador), terminado, 3 fotos y su video listo.
    - vieja: de Gabi (otro admin), sin publicar de hace tres días, sin fotos.
    - de_diego: de Diego (otro organizador), terminado, 2 fotos.
    - de_sofia: de Sofía (superadmin), terminado, 1 foto.
    - de_ana: de Ana (admin), terminado, 4 fotos.
    - abierto: de Ana, abierto desde hace dos días (vigente: no se borra).
    - futuro: de Bruno, sin publicar para dentro de diez días (vigente).
    """
    malena = nuevo_evento(
        db, cuentas["organizador"], "Cumple de 15 de Malena", "ma00le15", fotos=3,
        video_estado="listo", video_public_id="eventos/ma00le15/video-1700000000",
        video_url="https://res.cloudinary.com/nube/video/upload/eventos/ma00le15/video-1700000000.mp4",
        video_fotos=1, video_pedido_en=datetime(2026, 9, 22, 4, 0, tzinfo=timezone.utc),
    )
    return {
        "malena": malena,
        "vieja": nuevo_evento(db, cuentas["otro_admin"], "Aniversario sin publicar", "vi00ej00",
                              estado="borrador", fecha=HOY - timedelta(days=3), fotos=0),
        "de_diego": nuevo_evento(db, cuentas["otro_organizador"], "Egresados de Diego",
                                 "eg00re00", fotos=2),
        "de_sofia": nuevo_evento(db, cuentas["superadmin"], "Bautismo de Sofía", "so00fi00",
                                 fotos=1),
        "de_ana": nuevo_evento(db, cuentas["admin"], "Casamiento de Ana", "an00aa00", fotos=4),
        "abierto": nuevo_evento(db, cuentas["admin"], "Fiesta que sigue", "ab00ie00",
                                estado="activo", fecha=HOY - timedelta(days=2), fotos=2),
        "futuro": nuevo_evento(db, cuentas["organizador"], "Casamiento de Bruno", "fu00tu00",
                               estado="borrador", fecha=HOY + timedelta(days=10), fotos=0),
    }


def estado_de_la_base(db) -> dict[str, list[dict]]:
    """Cada fila de cada tabla de la app, columna por columna.

    Recorre `Base.metadata`, así una tabla nueva entra sola. Consultas de
    tablas y no de objetos: no pasan por el mapa de identidad de la sesión, así
    que ven siempre lo que está en la base."""
    return {
        tabla.name: [
            dict(fila._mapping)
            for fila in db.execute(select(tabla).order_by(*tabla.primary_key.columns))
        ]
        for tabla in Base.metadata.sorted_tables
    }


def sin_el_evento(estado: dict[str, list[dict]], id_evento: int) -> dict[str, list[dict]]:
    """Lo que tiene que quedar después de borrar ese evento: todo menos su fila
    y las de sus fotos."""
    return {
        **estado,
        "eventos": [f for f in estado["eventos"] if f["id"] != id_evento],
        "fotos": [f for f in estado["fotos"] if f["evento_id"] != id_evento],
    }


def existe(db, id_evento: int) -> bool:
    return db.scalar(select(Evento.id).where(Evento.id == id_evento)) is not None


def archivos_en_la_nube(nube: NubeFalsa, evento: Evento, fotos: int, videos: int = 1) -> None:
    """Carga en la nube falsa las imágenes de las filas y `videos` videos."""
    carpeta = f"eventos/{evento.codigo_publico}/"
    nube.archivos["image"] |= {f"{carpeta}f{i:02d}" for i in range(fotos)}
    nube.archivos["video"] |= {f"{carpeta}video-{i}" for i in range(videos)}


# ─────────────────────────────────────────────────────────────
# Quién puede
# ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("evento", ["malena", "de_diego", "de_ana"])
def test_un_organizador_recibe_403_y_no_se_toca_nada(cliente_con_base, cuentas, eventos, db,
                                                     evento):
    """Ni sobre un evento suyo (malena es de Bruno) ni sobre uno ajeno. El 403 va
    antes que todo: tampoco le dice si el evento existe ni qué le falta al cuerpo.
    Sin la fixture `nube`: si llamara a Cloudinary, la prueba fallaría."""
    bruno = cuentas["organizador"]
    objetivo = eventos[evento]
    antes = estado_de_la_base(db)

    r = borrar(cliente_con_base, objetivo.id, objetivo.nombre, actor=bruno)
    assert mensaje_de_error(r, "NO_AUTORIZADO", 403) == SIN_PERMISO
    sin_cuerpo = cliente_con_base.request("DELETE", RUTA.format(id=objetivo.id),
                                          headers=bearer_de(bruno))
    assert mensaje_de_error(sin_cuerpo, "NO_AUTORIZADO", 403) == SIN_PERMISO
    inexistente = borrar(cliente_con_base, 999999, "Lo que sea", actor=bruno)
    assert mensaje_de_error(inexistente, "NO_AUTORIZADO", 403) == SIN_PERMISO

    assert estado_de_la_base(db) == antes


def test_el_panel_sabe_que_a_un_organizador_no_se_le_ofrece(cliente_con_base, cuentas):
    """El panel ofrece *Borrar evento* sólo si `rol` es admin o superadmin
    (`esAdmin` de useSesion). El permiso de verdad es el 403 de arriba."""
    roles = {
        nombre: cliente_con_base.get("/api/admin/yo", headers=bearer_de(cuentas[nombre])).json()["rol"]
        for nombre in ("organizador", "admin", "superadmin")
    }
    assert roles == {"organizador": "organizador", "admin": "admin", "superadmin": "superadmin"}


def test_sin_sesion_o_con_un_token_que_no_sirve_es_401(cliente_con_base, cuentas, eventos, db):
    malena = eventos["malena"]
    antes = estado_de_la_base(db)
    for cabeceras in (None, {"Authorization": "Bearer no-es-un-token"}):
        r = cliente_con_base.request("DELETE", RUTA.format(id=malena.id), headers=cabeceras,
                                     json={"confirmar_nombre": malena.nombre})
        afirmar_error(r, "NO_AUTORIZADO", 401)
    assert estado_de_la_base(db) == antes


DE_CUALQUIER_CUENTA = ["malena", "vieja", "de_diego", "de_sofia", "de_ana"]
CASOS_ACTOR = [(a, e) for a in ("admin", "superadmin") for e in DE_CUALQUIER_CUENTA]


@pytest.mark.parametrize("actor,evento", CASOS_ACTOR, ids=[f"{a}-{e}" for a, e in CASOS_ACTOR])
def test_admin_y_superadmin_borran_eventos_de_cualquier_cuenta(cliente_con_base, cuentas, eventos,
                                                               db, nube, actor, evento):
    """De un organizador, de otro admin, de un superadmin y los propios. Se va
    ese evento con sus fotos, y nada más."""
    objetivo = eventos[evento]
    fotos = len([f for f in estado_de_la_base(db)["fotos"] if f["evento_id"] == objetivo.id])
    antes = estado_de_la_base(db)

    r = borrar(cliente_con_base, objetivo.id, objetivo.nombre, actor=cuentas[actor])

    assert r.status_code == 200, r.text
    assert r.json() == {"eliminado": True, "fotos": fotos}
    assert estado_de_la_base(db) == sin_el_evento(antes, objetivo.id), (
        "se fueron el evento y sus fotos, y ninguna otra fila"
    )
    assert set(nube.prefijos()) == {("image", f"eventos/{objetivo.codigo_publico}/"),
                                    ("video", f"eventos/{objetivo.codigo_publico}/")}


def test_el_dueno_ya_no_lo_ve_en_su_historial(cliente_con_base, cuentas, eventos, nube):
    bruno = cuentas["organizador"]
    historial = "/api/admin/eventos?alcance=historial"
    antes = [e["nombre"] for e in cliente_con_base.get(historial, headers=bearer_de(bruno)).json()]
    assert antes == ["Cumple de 15 de Malena"]

    r = borrar(cliente_con_base, eventos["malena"].id, "Cumple de 15 de Malena",
               actor=cuentas["admin"])
    assert r.status_code == 200, r.text

    assert cliente_con_base.get(historial, headers=bearer_de(bruno)).json() == []
    todos = cliente_con_base.get("/api/admin/eventos", headers=bearer_de(cuentas["admin"])).json()
    assert "Cumple de 15 de Malena" not in [e["nombre"] for e in todos]


# ─────────────────────────────────────────────────────────────
# Sólo eventos del Historial
# ─────────────────────────────────────────────────────────────

# (estado, días desde hoy, ¿es del Historial?)
CASOS_HISTORIAL = [
    ("cerrado", -40, True), ("cerrado", -1, True), ("cerrado", 0, True), ("cerrado", 10, True),
    ("borrador", -40, True), ("borrador", -1, True),
    ("borrador", 0, False), ("borrador", 1, False), ("borrador", 60, False),
    ("activo", -40, False), ("activo", -1, False), ("activo", 0, False), ("activo", 10, False),
]


@pytest.mark.parametrize(
    "estado,dias,del_historial", CASOS_HISTORIAL,
    ids=[f"{e}{d:+d}" for e, d, _ in CASOS_HISTORIAL],
)
def test_solo_eventos_del_historial(cliente_con_base, cuentas, db, nube, estado, dias,
                                    del_historial):
    """Terminado de cualquier fecha, o sin publicar de fecha pasada: se borra.
    Abierto de cualquier fecha, o sin publicar de hoy en adelante: 422, y no se
    toca nada. Es exactamente lo que el listado muestra en el Historial."""
    ana = cuentas["admin"]
    evento = nuevo_evento(db, cuentas["organizador"], "El evento", "hi00st00", estado=estado,
                          fecha=HOY + timedelta(days=dias), fotos=2)

    en_el_listado = [e["id"] for e in cliente_con_base.get(
        "/api/admin/eventos?alcance=historial", headers=bearer_de(ana)).json()]
    assert (evento.id in en_el_listado) is del_historial, "el mismo criterio que el listado"

    antes = estado_de_la_base(db)
    r = borrar(cliente_con_base, evento.id, "El evento", actor=ana)

    if del_historial:
        assert r.status_code == 200, r.text
        assert r.json() == {"eliminado": True, "fotos": 2}
        assert not existe(db, evento.id)
        return
    assert mensaje_de_error(r, "DATOS_INVALIDOS", 422) == SOLO_DEL_HISTORIAL
    assert estado_de_la_base(db) == antes
    assert nube.pedidos == [], "un rechazo no llama a Cloudinary"


def test_un_evento_sin_publicar_de_hoy_se_puede_borrar_desde_manana(cliente_con_base, cuentas,
                                                                     db, nube, monkeypatch):
    """"Hoy" es el de Argentina que usa el listado (regla de medianoche)."""
    evento = nuevo_evento(db, cuentas["organizador"], "Esta noche", "no00ch00",
                          estado="borrador", fecha=HOY, fotos=0)
    r = borrar(cliente_con_base, evento.id, "Esta noche", actor=cuentas["admin"])
    assert mensaje_de_error(r, "DATOS_INVALIDOS", 422) == SOLO_DEL_HISTORIAL

    monkeypatch.setattr(rutas_admin, "hoy_en_argentina", lambda: HOY + timedelta(days=1))
    r = borrar(cliente_con_base, evento.id, "Esta noche", actor=cuentas["admin"])
    assert r.status_code == 200, r.text
    assert r.json() == {"eliminado": True, "fotos": 0}


def test_terminarlo_primero_y_despues_borrarlo(cliente_con_base, cuentas, eventos, db, nube):
    """Lo que dice el mensaje: uno abierto se termina y después se borra."""
    ana, abierto = cuentas["admin"], eventos["abierto"]
    r = borrar(cliente_con_base, abierto.id, abierto.nombre, actor=ana)
    assert mensaje_de_error(r, "DATOS_INVALIDOS", 422) == SOLO_DEL_HISTORIAL

    cerrar = cliente_con_base.patch(RUTA.format(id=abierto.id), json={"estado": "cerrado"},
                                    headers=bearer_de(ana))
    assert cerrar.status_code == 200, cerrar.text

    r = borrar(cliente_con_base, abierto.id, abierto.nombre, actor=ana)
    assert r.status_code == 200, r.text
    assert r.json() == {"eliminado": True, "fotos": 2}


# ─────────────────────────────────────────────────────────────
# Confirmar el nombre, inexistentes y cuerpos mal formados
# ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("escrito", [
    "",
    "   ",
    "Cumple de 15",
    "Cumple de 15 de Malena!",
    "Cumple de 15 deMalena",         # un espacio de menos no es "espacios de sobra"
    "Cumple de 15 de Malena.",
    "Cumple de 15 de M\u0430lena",    # una "а" cirílica: se ve igual y no es la misma
    "Egresados de Diego",            # el nombre de OTRO evento
])
def test_si_el_nombre_no_coincide_no_se_borra_nada(cliente_con_base, cuentas, eventos, db,
                                                   escrito):
    """Sin `nube`: un rechazo no llega a Cloudinary."""
    malena = eventos["malena"]
    antes = estado_de_la_base(db)
    r = borrar(cliente_con_base, malena.id, escrito, actor=cuentas["superadmin"])
    assert mensaje_de_error(r, "DATOS_INVALIDOS", 422) == NO_COINCIDE
    assert estado_de_la_base(db) == antes


@pytest.mark.parametrize("escrito", [
    "Cumple de 15 de Malena",
    "cumple de 15 de malena",
    "CUMPLE DE 15 DE MALENA",
    "   Cumple de 15 de Malena   ",
    "\tcUMPLE de 15 de malena\n",
    "Cumple de 15  de Malena",          # espacios de sobra adentro: se juntan en uno
    "Cumple de 15 de   Malena",    # uno duro (pegado de otro lado) y tres seguidos
    "Cumple de 15 de\tMalena",
])
def test_el_nombre_se_compara_como_se_ve(cliente_con_base, cuentas, eventos, db, nube, escrito):
    """Sin mayúsculas, sin espacios alrededor y con los de adentro juntados: lo
    que hace `normalizar` en comp/Confirmar.tsx, el diálogo del panel."""
    r = borrar(cliente_con_base, eventos["malena"].id, escrito, actor=cuentas["admin"])
    assert r.status_code == 200, r.text
    assert not existe(db, eventos["malena"].id)


def test_un_nombre_guardado_con_espacio_doble_se_borra_escribiendo_lo_que_se_ve(
        cliente_con_base, cuentas, db, nube):
    """El navegador junta los espacios al mostrar el nombre (y al copiarlo), y en
    el celular dos espacios seguidos escriben ". ": nadie podría escribir el doble."""
    evento = nuevo_evento(db, cuentas["organizador"], "Boda  de   Ana", "bo00da00", fotos=1)
    r = borrar(cliente_con_base, evento.id, "boda de ana", actor=cuentas["admin"])
    assert r.status_code == 200, r.text
    assert r.json() == {"eliminado": True, "fotos": 1}


@pytest.mark.parametrize("guardado,escrito", [
    ("Bautismo de Sofía", "Bautismo de Sofía"),   # guardado en NFD (macOS), escrito en NFC
    ("Bautismo de Sofía", "bautismo de sofía"),   # al revés
], ids=["nfd-guardado", "nfd-escrito"])
def test_las_tildes_se_comparan_en_una_sola_forma(cliente_con_base, cuentas, db, nube, guardado,
                                                  escrito):
    evento = nuevo_evento(db, cuentas["organizador"], guardado, "nf00dd00", fotos=0)
    r = borrar(cliente_con_base, evento.id, escrito, actor=cuentas["admin"])
    assert r.status_code == 200, r.text


@pytest.mark.parametrize("nombre", [" ", "   ", "\t", " ", " \n "])
def test_un_evento_no_se_crea_con_un_nombre_en_blanco(cliente_con_base, cuentas, nombre):
    """Se recorta ANTES de medir (NombreEvento). Si no, quedaba guardado como "" y
    un campo vacío "coincidía" con él: el diálogo habilitaba Borrar sin escribir
    nada, y el backend lo aceptaba."""
    bruno = bearer_de(cuentas["organizador"])
    r = cliente_con_base.post("/api/admin/eventos", headers=bruno,
                              json={"nombre": nombre, "fecha_evento": "2026-12-01"})
    afirmar_error(r, "DATOS_INVALIDOS", 422)

    ok = cliente_con_base.post("/api/admin/eventos", headers=bruno,
                               json={"nombre": f"{nombre}Cumple{nombre}", "fecha_evento": "2026-12-01"})
    assert ok.status_code == 201, ok.text
    assert ok.json()["nombre"] == "Cumple"


@pytest.mark.parametrize("escrito", ["", "   ", " "])
def test_un_evento_de_nombre_en_blanco_no_se_borra_con_el_campo_vacio(cliente_con_base, cuentas,
                                                                      db, escrito):
    """Uno de antes de NombreEvento, guardado en blanco: lo vacío nunca coincide.
    Sin `nube`: tampoco llega a Cloudinary."""
    evento = nuevo_evento(db, cuentas["organizador"], "", "en00bl00", fotos=2)
    antes = estado_de_la_base(db)
    r = borrar(cliente_con_base, evento.id, escrito, actor=cuentas["admin"])
    assert mensaje_de_error(r, "DATOS_INVALIDOS", 422) == NO_COINCIDE
    assert estado_de_la_base(db) == antes


def test_uno_abierto_con_otro_nombre_dice_primero_que_no_es_del_historial(
        cliente_con_base, cuentas, eventos, db):
    """El orden de la sección 5: Historial (422) antes que el nombre (422). Sin
    `nube`: el rechazo tampoco llama a Cloudinary."""
    antes = estado_de_la_base(db)
    r = borrar(cliente_con_base, eventos["abierto"].id, "Otro nombre", actor=cuentas["admin"])
    assert mensaje_de_error(r, "DATOS_INVALIDOS", 422) == SOLO_DEL_HISTORIAL
    assert estado_de_la_base(db) == antes


def test_con_tildes_y_mayusculas(cliente_con_base, cuentas, eventos, db, nube):
    r = borrar(cliente_con_base, eventos["de_sofia"].id, "  BAUTISMO DE SOFÍA ",
               actor=cuentas["admin"])
    assert r.status_code == 200, r.text


def test_evento_inexistente(cliente_con_base, cuentas, eventos, db):
    antes = estado_de_la_base(db)
    r = borrar(cliente_con_base, 999999, "Cumple de 15 de Malena", actor=cuentas["admin"])
    assert mensaje_de_error(r, "EVENTO_NO_ENCONTRADO", 404) == NO_EXISTE
    assert estado_de_la_base(db) == antes


def test_un_id_que_no_entra_en_bigint(cliente_con_base, cuentas, eventos, db):
    antes = estado_de_la_base(db)
    r = borrar(cliente_con_base, 10**20, "Cumple de 15 de Malena", actor=cuentas["admin"])
    afirmar_error(r, "DATOS_INVALIDOS", 422)
    assert estado_de_la_base(db) == antes


def test_borrarlo_dos_veces_la_segunda_es_404(cliente_con_base, cuentas, eventos, db, nube):
    malena = eventos["malena"]
    assert borrar(cliente_con_base, malena.id, malena.nombre, actor=cuentas["admin"]).status_code == 200
    pedidos = len(nube.pedidos)
    antes = estado_de_la_base(db)

    r = borrar(cliente_con_base, malena.id, malena.nombre, actor=cuentas["superadmin"])
    assert mensaje_de_error(r, "EVENTO_NO_ENCONTRADO", 404) == NO_EXISTE
    assert estado_de_la_base(db) == antes
    assert len(nube.pedidos) == pedidos


@pytest.mark.parametrize("cuerpo", [
    None,
    {},
    {"nombre": "Cumple de 15 de Malena"},
    {"confirmar_nombre": None},
    {"confirmar_nombre": 15},
    {"confirmar_nombre": ["Cumple de 15 de Malena"]},
    {"confirmar_nombre": "x" * 201},
], ids=["sin-cuerpo", "vacio", "otro-campo", "null", "numero", "lista", "largo"])
def test_un_cuerpo_mal_formado_es_datos_invalidos(cliente_con_base, cuentas, eventos, db, cuerpo):
    antes = estado_de_la_base(db)
    r = cliente_con_base.request("DELETE", RUTA.format(id=eventos["malena"].id), json=cuerpo,
                                 headers=bearer_de(cuentas["admin"]))
    assert mensaje_de_error(r, "DATOS_INVALIDOS", 422) == DATOS_INVALIDOS
    assert estado_de_la_base(db) == antes


# ─────────────────────────────────────────────────────────────
# Cloudinary: prefijo exacto, imágenes y videos, paginado
# ─────────────────────────────────────────────────────────────

def test_borra_imagenes_y_videos_con_el_prefijo_exacto_y_paginado(cliente_con_base, cuentas, db,
                                                                   nube):
    """El prefijo lleva la barra final: `eventos/ab12` es prefijo de
    `eventos/ab123/…`, que es otro evento, y sus archivos tienen que quedar.
    Cloudinary borra de a `por_pedido` y avisa con `next_cursor`: se repite
    hasta que no avisa más, con `invalidate` y basic auth en cada pedido."""
    bruno = cuentas["organizador"]
    evento = nuevo_evento(db, bruno, "Cumple de Juan", "ab12", fotos=5,
                          video_estado="listo", video_public_id="eventos/ab12/video-1")
    vecino = nuevo_evento(db, bruno, "Cumple de Juana", "ab123", fotos=2)
    nube.por_pedido = 2
    nube.archivos["image"] = {f"eventos/ab12/f{i:02d}" for i in range(5)} | {
        "eventos/ab123/f00", "eventos/ab123/f01",
    }
    nube.archivos["video"] = {"eventos/ab12/video-1", "eventos/ab12/video-2",
                              "eventos/ab123/video-9"}

    r = borrar(cliente_con_base, evento.id, "Cumple de Juan", actor=cuentas["admin"])

    assert r.status_code == 200, r.text
    assert r.json() == {"eliminado": True, "fotos": 5}
    assert nube.archivos == {
        "image": {"eventos/ab123/f00", "eventos/ab123/f01"},
        "video": {"eventos/ab123/video-9"},
    }, "todo lo del evento, fotos y videos, y nada del vecino"
    assert nube.prefijos() == [("image", "eventos/ab12/")] * 3 + [("video", "eventos/ab12/")]
    assert [p["params"].get("next_cursor") for p in nube.pedidos] == [
        None, "cursor-1", "cursor-2", None,
    ], "cada vuelta manda el cursor de la anterior"
    for pedido in nube.pedidos:
        assert pedido["url"] == (
            f"https://api.cloudinary.com/v1_1/{NUBE}/resources/{pedido['tipo']}/upload"
        )
        assert pedido["params"]["invalidate"] == "true"
        assert pedido["auth"] == (CLAVE, SECRETO)
        assert SECRETO not in str(pedido["params"]), "el secreto no va en la URL"
    assert existe(db, vecino.id)
    assert len([f for f in estado_de_la_base(db)["fotos"] if f["evento_id"] == vecino.id]) == 2


def test_con_las_fotos_ya_borradas_no_llama_a_cloudinary(cliente_con_base, cuentas, db):
    """Sin `nube`: el fixture automático hace fallar cualquier DELETE a Cloudinary."""
    evento = nuevo_evento(db, cuentas["organizador"], "Egresados 2025", "eg20ve25",
                          fecha=HOY - timedelta(days=45), fotos=3,
                          fotos_borradas_en=datetime(2026, 9, 1, 12, tzinfo=timezone.utc))
    antes = estado_de_la_base(db)

    r = borrar(cliente_con_base, evento.id, "Egresados 2025", actor=cuentas["superadmin"])

    assert r.status_code == 200, r.text
    assert r.json() == {"eliminado": True, "fotos": 3}, "las filas sí se cuentan y se borran"
    assert estado_de_la_base(db) == sin_el_evento(antes, evento.id)


def test_vencido_pero_sin_pasada_todavia_si_llama_a_cloudinary(cliente_con_base, cuentas, db,
                                                               nube):
    """Desde el día del borrado los archivos ya no se ofrecen, pero si la pasada
    todavía no corrió siguen en Cloudinary: `fotos_borradas_en` es lo que manda."""
    evento = nuevo_evento(db, cuentas["organizador"], "Vencido", "ve00nc00",
                          fecha=HOY - timedelta(days=40), fotos=2)
    archivos_en_la_nube(nube, evento, fotos=2)

    r = borrar(cliente_con_base, evento.id, "Vencido", actor=cuentas["admin"])

    assert r.status_code == 200, r.text
    assert nube.prefijos() == [("image", "eventos/ve00nc00/"), ("video", "eventos/ve00nc00/")]
    assert nube.archivos == {"image": set(), "video": set()}


FALLAS = {
    "http-500": lambda tipo, params: httpx.Response(500, text="error interno"),
    "rate-limit": lambda tipo, params: httpx.Response(420, text="Rate Limit Exceeded"),
    "sin-red": lambda tipo, params: httpx.ConnectError("sin red"),
    "no-es-json": lambda tipo, params: httpx.Response(200, text="<html>no</html>"),
    # Las imágenes salen y el video no: quedó a medio borrar.
    "video-a-mitad": lambda tipo, params: (
        httpx.Response(500, text="Cloudinary está caído") if tipo == "video" else None
    ),
}


@pytest.mark.parametrize("falla", list(FALLAS))
def test_si_cloudinary_falla_no_se_borra_nada_de_la_base(cliente_con_base, cuentas, eventos, db,
                                                         nube, caplog, falla):
    """503 con un mensaje claro, la base como estaba y el lock suelto: volver a
    probar anda, porque borrar en Cloudinary lo que ya no está no es error."""
    malena = eventos["malena"]
    archivos_en_la_nube(nube, malena, fotos=3, videos=2)
    nube.falla = FALLAS[falla]
    antes = estado_de_la_base(db)

    with caplog.at_level(logging.ERROR, logger=rutas_admin.log_eventos.name):
        r = borrar(cliente_con_base, malena.id, malena.nombre, actor=cuentas["admin"])

    assert mensaje_de_error(r, "DATOS_INVALIDOS", 503) == NO_SE_BORRARON
    assert estado_de_la_base(db) == antes, "ni las fotos ni el evento"
    assert nube.pedidos, "sí se intentó"
    assert f"evento {malena.id}" in caplog.text and "no se borró nada" in caplog.text
    for dato in (SECRETO, CLAVE, malena.nombre):
        assert dato not in caplog.text

    # Cloudinary vuelve: el mismo pedido anda, y ahora sí se va todo.
    nube.falla = None
    r = borrar(cliente_con_base, malena.id, malena.nombre, actor=cuentas["admin"])
    assert r.status_code == 200, r.text
    assert nube.archivos == {"image": set(), "video": set()}
    assert estado_de_la_base(db) == sin_el_evento(antes, malena.id)


def test_la_pasada_de_limpieza_sigue_andando_despues_de_una_falla(cliente_con_base, cuentas, db,
                                                                   nube, motor_prueba):
    """Si el borrado falla, el evento queda sin marcar y la pasada de los 30
    días lo sigue tomando como a cualquier otro: no quedó trabado."""
    evento = nuevo_evento(db, cuentas["organizador"], "Vencido", "ve00nc00",
                          fecha=HOY - timedelta(days=40), fotos=1)
    nube.falla = lambda tipo, params: httpx.Response(500, text="caído")
    r = borrar(cliente_con_base, evento.id, "Vencido", actor=cuentas["admin"])
    afirmar_error(r, "DATOS_INVALIDOS", 503)

    nube.falla = None
    fabrica = sessionmaker(bind=motor_prueba, autoflush=False, expire_on_commit=False)
    assert limpieza.pasada_de_limpieza(hoy=HOY, fabrica_de_sesiones=fabrica) == 1


# ─────────────────────────────────────────────────────────────
# Después: nada colgado, y las claves públicas dan 404
# ─────────────────────────────────────────────────────────────

def claves_hacia_eventos(db) -> list[tuple[str, str]]:
    """(tabla, columna) de cada clave foránea de la base que apunta a `eventos`,
    leídas del catálogo de Postgres y no de los modelos."""
    filas = db.execute(text(
        "SELECT c.conrelid::regclass::text, a.attname "
        "FROM pg_constraint c "
        "JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY (c.conkey) "
        "WHERE c.contype = 'f' AND c.confrelid = 'eventos'::regclass "
        "ORDER BY 1, 2"
    )).all()
    return [(tabla, columna) for tabla, columna in filas]


def test_no_queda_ninguna_fila_colgada(cliente_con_base, cuentas, eventos, db, nube):
    """Ninguna fila de ninguna tabla sigue apuntando al evento borrado. Si algún
    día aparece otra tabla con una clave hacia `eventos` (una de pedidos de
    video, de vinculaciones…), esta prueba avisa: `borrar_evento` tiene que
    borrar esas filas también."""
    claves = claves_hacia_eventos(db)
    assert claves == [("fotos", "evento_id")], (
        f"hay claves nuevas hacia eventos: {claves}. Sumalas a borrar_evento y a esta prueba"
    )
    malena = eventos["malena"]
    fotos_antes = [f["id"] for f in estado_de_la_base(db)["fotos"] if f["evento_id"] == malena.id]
    assert len(fotos_antes) == 3

    r = borrar(cliente_con_base, malena.id, malena.nombre, actor=cuentas["admin"])
    assert r.status_code == 200, r.text

    for tabla, columna in claves:
        colgadas = db.execute(
            text(f"SELECT count(*) FROM {tabla} WHERE {columna} = :id"), {"id": malena.id}
        ).scalar()
        assert colgadas == 0, f"{tabla}.{columna} sigue apuntando al evento borrado"
    assert db.scalar(select(Foto.id).where(Foto.id.in_(fotos_antes))) is None
    assert db.scalar(
        select(Foto.id).where(Foto.public_id.like(f"eventos/{malena.codigo_publico}/%"))
    ) is None
    # El video del evento (sus columnas) se fue con la fila, y su archivo con el prefijo.
    assert db.scalar(select(Evento.id).where(Evento.codigo_publico == malena.codigo_publico)) is None
    assert ("video", f"eventos/{malena.codigo_publico}/") in nube.prefijos()


def test_el_codigo_publico_y_el_token_de_pantalla_dan_404(cliente_con_base, cuentas, eventos, nube):
    malena = eventos["malena"]
    codigo, token = malena.codigo_publico, malena.token_pantalla
    ana = bearer_de(cuentas["admin"])
    # Antes: terminado, el invitado ve que terminó y la pantalla sigue pasando las aprobadas.
    assert cliente_con_base.get(f"/api/e/{codigo}").json()["estado"] == "cerrado"
    assert cliente_con_base.get(f"/api/pantalla/{token}").status_code == 200
    assert len(cliente_con_base.get(f"/api/pantalla/{token}/fotos?desde=0").json()["fotos"]) == 1

    r = borrar(cliente_con_base, malena.id, malena.nombre, actor=cuentas["admin"])
    assert r.status_code == 200, r.text

    for respuesta in (
        cliente_con_base.get(f"/api/e/{codigo}"),
        cliente_con_base.post(f"/api/e/{codigo}/firma", json={"dispositivo_hash": "f" * 32}),
        cliente_con_base.get(f"/api/pantalla/{token}"),
        cliente_con_base.get(f"/api/pantalla/{token}/fotos?desde=0"),
    ):
        afirmar_error(respuesta, "EVENTO_NO_ENCONTRADO", 404)
    # Y en el panel, el id tampoco existe más.
    for respuesta in (
        cliente_con_base.get(f"/api/admin/eventos/{malena.id}/fotos", headers=ana),
        cliente_con_base.get(f"/api/admin/eventos/{malena.id}/resumen", headers=ana),
        cliente_con_base.get(f"/api/admin/eventos/{malena.id}/video", headers=ana),
        cliente_con_base.get(f"/api/admin/eventos/{malena.id}/descarga", headers=ana),
        cliente_con_base.patch(RUTA.format(id=malena.id), json={"estado": "activo"}, headers=ana),
    ):
        afirmar_error(respuesta, "EVENTO_NO_ENCONTRADO", 404)


def test_un_codigo_de_vinculacion_vivo_deja_de_servir(cliente_con_base, cuentas, eventos, nube):
    """Un evento terminado se puede conectar a una tele (la pantalla sigue
    pasando las aprobadas). Si se borra, el código de seis dígitos que estaba
    vivo ya no entrega su token; el de otro evento sigue andando."""
    ana = bearer_de(cuentas["admin"])
    malena, de_diego = eventos["malena"], eventos["de_diego"]
    codigo = cliente_con_base.post(f"/api/admin/eventos/{malena.id}/vincular", headers=ana).json()["codigo"]
    otro = cliente_con_base.post(f"/api/admin/eventos/{de_diego.id}/vincular", headers=ana).json()["codigo"]

    r = borrar(cliente_con_base, malena.id, malena.nombre, actor=cuentas["admin"])
    assert r.status_code == 200, r.text

    afirmar_error(cliente_con_base.post("/api/pantalla/canjear", json={"codigo": codigo}),
                  "EVENTO_NO_ENCONTRADO", 404)
    canje = cliente_con_base.post("/api/pantalla/canjear", json={"codigo": otro})
    assert canje.status_code == 200, canje.text
    assert canje.json() == {"token_pantalla": de_diego.token_pantalla}


def test_anular_del_evento_solo_quema_los_de_ese_evento():
    vinculacion.crear(1, "token-uno")
    vinculacion.crear(2, "token-dos")
    assert vinculacion.anular_del_evento(1) == 1
    assert vinculacion.anular_del_evento(1) == 0
    assert [v.evento_id for v in vinculacion._por_codigo.values()] == [2]


# ─────────────────────────────────────────────────────────────
# Una transacción, y las carreras
# ─────────────────────────────────────────────────────────────

def test_todo_en_una_transaccion(cliente_con_base, cuentas, db, monkeypatch):
    """Si el DELETE del evento falla después de borrar las fotos, no queda nada
    a medias: las fotos vuelven con el rollback. (Con las fotos ya borradas de
    Cloudinary, para que esto pruebe sólo la base.)"""
    evento = nuevo_evento(db, cuentas["organizador"], "A medias", "am00ed00", fotos=3,
                          fotos_borradas_en=datetime(2026, 9, 25, tzinfo=timezone.utc))
    delete_de_verdad = rutas_admin.delete

    class FallaAlBorrarElEvento:
        def where(self, *_args):
            return text("SELECT 1 / 0")

    def delete_que_falla(tabla):
        return FallaAlBorrarElEvento() if tabla is Evento else delete_de_verdad(tabla)

    monkeypatch.setattr(rutas_admin, "delete", delete_que_falla)
    antes = estado_de_la_base(db)

    r = borrar(cliente_con_base, evento.id, "A medias", actor=cuentas["admin"])

    assert r.status_code >= 400
    assert estado_de_la_base(db) == antes


def esperar_a_que_alguien_espere_un_lock(motor, segundos: float = 10.0) -> None:
    """Hasta que alguna conexión de la base de pruebas quede esperando un lock.
    Cada vuelta en su propia transacción: pg_stat_activity se lee una vez por
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
    raise AssertionError("nadie quedó esperando el lock del evento")


class NubeQueSeTraba:
    """La nube falsa, pero el PRIMER pedido se queda esperando hasta `soltar`.
    `adentro` avisa que ese primer pedido ya llegó."""

    def __init__(self, nube: NubeFalsa) -> None:
        self.nube = nube
        self.adentro = threading.Event()
        self.soltar = threading.Event()
        self.llamadas = 0

    def delete(self, url, **kwargs):
        self.llamadas += 1
        if not self.adentro.is_set():
            self.adentro.set()
            assert self.soltar.wait(15), "nadie soltó la nube"
        return self.nube.delete(url, **kwargs)


@pytest.fixture()
def nube_trabada(monkeypatch) -> NubeQueSeTraba:
    trabada = NubeQueSeTraba(NubeFalsa())
    monkeypatch.setattr(httpx, "delete", trabada.delete)
    return trabada


def en_un_hilo(resultados: dict, clave: str, funcion) -> threading.Thread:
    def correr():
        try:
            resultados[clave] = funcion()
        except Exception as e:  # noqa: BLE001 — la prueba lo mira después
            resultados[clave] = e
    hilo = threading.Thread(target=correr, daemon=True)
    hilo.start()
    return hilo


@pytest.fixture()
def fabrica(motor_prueba):
    return sessionmaker(bind=motor_prueba, autoflush=False, expire_on_commit=False)


def test_si_la_pasada_de_limpieza_lo_tiene_tomado_el_borrado_espera(
    cliente_con_base, cuentas, db, motor_prueba, fabrica, nube_trabada,
):
    """La pasada toma el evento vencido y se queda en Cloudinary. El borrado
    espera el lock; cuando la pasada marca `fotos_borradas_en` y suelta, el
    borrado lo ve y NO vuelve a pedir el borrado a Cloudinary."""
    evento = nuevo_evento(db, cuentas["organizador"], "Vencido", "ve00nc00",
                          fecha=HOY - timedelta(days=40), fotos=2)
    archivos_en_la_nube(nube_trabada.nube, evento, fotos=2)
    resultados: dict = {}

    pasada = en_un_hilo(resultados, "pasada",
                        lambda: limpieza.pasada_de_limpieza(hoy=HOY, fabrica_de_sesiones=fabrica))
    borrado = None
    try:
        assert nube_trabada.adentro.wait(15), "la pasada no llegó a Cloudinary"
        borrado = en_un_hilo(resultados, "borrado", lambda: borrar(
            cliente_con_base, evento.id, "Vencido", actor=cuentas["admin"]))
        esperar_a_que_alguien_espere_un_lock(motor_prueba)
    finally:
        nube_trabada.soltar.set()
        pasada.join(15)
        if borrado is not None:
            borrado.join(15)

    assert resultados["pasada"] == 1
    r = resultados["borrado"]
    assert r.status_code == 200, r.text
    assert r.json() == {"eliminado": True, "fotos": 2}
    assert Counter(nube_trabada.nube.prefijos()) == {
        ("image", "eventos/ve00nc00/"): 1, ("video", "eventos/ve00nc00/"): 1,
    }, "cada carpeta se pidió una sola vez: la de la pasada"
    assert not existe(db, evento.id)


def test_si_el_borrado_lo_tiene_tomado_la_pasada_lo_saltea(
    cliente_con_base, cuentas, db, fabrica, nube_trabada,
):
    """Al revés: el borrado toma el evento y se queda en Cloudinary. La pasada
    lo saltea (SKIP LOCKED) sin esperar ni pedir nada; cuando el borrado
    termina, el evento ya no existe y ninguna pasada lo vuelve a tomar."""
    evento = nuevo_evento(db, cuentas["organizador"], "Vencido", "ve00nc00",
                          fecha=HOY - timedelta(days=40), fotos=2)
    archivos_en_la_nube(nube_trabada.nube, evento, fotos=2)
    resultados: dict = {}

    borrado = en_un_hilo(resultados, "borrado", lambda: borrar(
        cliente_con_base, evento.id, "Vencido", actor=cuentas["superadmin"]))
    try:
        assert nube_trabada.adentro.wait(15), "el borrado no llegó a Cloudinary"
        inicio = time.monotonic()
        assert limpieza.pasada_de_limpieza(hoy=HOY, fabrica_de_sesiones=fabrica) == 0
        assert time.monotonic() - inicio < 5, "la pasada no esperó el lock"
        assert nube_trabada.llamadas == 1, "la pasada no pidió nada a Cloudinary"
    finally:
        nube_trabada.soltar.set()
        borrado.join(15)

    r = resultados["borrado"]
    assert r.status_code == 200, r.text
    assert Counter(nube_trabada.nube.prefijos()) == {
        ("image", "eventos/ve00nc00/"): 1, ("video", "eventos/ve00nc00/"): 1,
    }
    assert not existe(db, evento.id)
    assert limpieza.pasada_de_limpieza(hoy=HOY, fabrica_de_sesiones=fabrica) == 0


def test_dos_borrados_a_la_vez_el_segundo_espera_y_da_404(
    cliente_con_base, cuentas, eventos, db, motor_prueba, nube_trabada,
):
    malena = eventos["malena"]
    archivos_en_la_nube(nube_trabada.nube, malena, fotos=3)
    resultados: dict = {}

    primero = en_un_hilo(resultados, "primero", lambda: borrar(
        cliente_con_base, malena.id, malena.nombre, actor=cuentas["admin"]))
    segundo = None
    try:
        assert nube_trabada.adentro.wait(15)
        segundo = en_un_hilo(resultados, "segundo", lambda: borrar(
            cliente_con_base, malena.id, malena.nombre, actor=cuentas["superadmin"]))
        esperar_a_que_alguien_espere_un_lock(motor_prueba)
    finally:
        nube_trabada.soltar.set()
        primero.join(15)
        if segundo is not None:
            segundo.join(15)

    assert resultados["primero"].status_code == 200, resultados["primero"].text
    afirmar_error(resultados["segundo"], "EVENTO_NO_ENCONTRADO", 404)
    assert Counter(nube_trabada.nube.prefijos()) == {
        ("image", "eventos/ma00le15/"): 1, ("video", "eventos/ma00le15/"): 1,
    }


def test_una_foto_que_llega_mientras_se_borra_no_queda_colgada(
    cliente_con_base, cuentas, eventos, db, fabrica, nube_trabada,
):
    """El alta de una foto necesita FOR KEY SHARE sobre su evento (la clave
    foránea): mientras el borrado lo tiene tomado, espera; cuando termina, el
    evento ya no existe y el alta falla. Ninguna foto queda apuntando a nada."""
    malena = eventos["malena"]
    resultados: dict = {}
    foto = {"public_id": "eventos/ma00le15/tarde", "url": url_de("eventos/ma00le15/tarde")}

    borrado = en_un_hilo(resultados, "borrado", lambda: borrar(
        cliente_con_base, malena.id, malena.nombre, actor=cuentas["admin"]))
    try:
        assert nube_trabada.adentro.wait(15)
        with fabrica() as invitado:
            invitado.execute(text("SET LOCAL lock_timeout = '300ms'"))
            invitado.add(Foto(evento_id=malena.id, **foto))
            with pytest.raises(OperationalError, match="lock timeout"):
                invitado.commit()
    finally:
        nube_trabada.soltar.set()
        borrado.join(15)

    assert resultados["borrado"].status_code == 200, resultados["borrado"].text
    with fabrica() as invitado:
        invitado.add(Foto(evento_id=malena.id, **foto))
        with pytest.raises(IntegrityError):
            invitado.commit()
    assert db.execute(
        text("SELECT count(*) FROM fotos WHERE evento_id = :id"), {"id": malena.id}
    ).scalar() == 0


# ─────────────────────────────────────────────────────────────
# Un video que Cloudinary está armando
# ─────────────────────────────────────────────────────────────

class ConsultasDeVideo:
    """consultar_video de mentira: anota qué se preguntó y contesta `url`."""

    def __init__(self, url: str | None) -> None:
        self.url = url
        self.pedidos: list[str] = []

    def __call__(self, public_id: str) -> str | None:
        self.pedidos.append(public_id)
        return self.url


def con_video_armandose(db, dueno: Usuario, nombre: str, codigo: str, *,
                        hace: timedelta = timedelta(minutes=1), **extra) -> Evento:
    """Terminado hace cinco días (salvo que `extra` diga otra cosa), con 3 fotos
    y un video pedido a Cloudinary hace `hace`."""
    return nuevo_evento(
        db, dueno, nombre, codigo, fotos=3,
        video_estado="procesando", video_public_id=f"eventos/{codigo}/video-1790544847",
        video_fotos=1, video_pedido_en=datetime.now(timezone.utc) - hace, **extra,
    )


def test_con_el_video_armandose_no_se_borra(cliente_con_base, cuentas, db, monkeypatch):
    """El MP4 aparece en la carpeta minutos DESPUÉS del pedido: si el borrado por
    prefijo pasara antes, quedaría publicado para siempre, sin fila que lo
    recuerde. 422, y no se toca nada (sin `nube`: tampoco se borra en Cloudinary)."""
    evento = con_video_armandose(db, cuentas["organizador"], "Cumple de Juan", "ca00rr00")
    consultas = ConsultasDeVideo(url=None)
    monkeypatch.setattr(rutas_admin, "consultar_video", consultas)
    antes = estado_de_la_base(db)

    r = borrar(cliente_con_base, evento.id, "Cumple de Juan", actor=cuentas["admin"])

    assert mensaje_de_error(r, "DATOS_INVALIDOS", 422) == VIDEO_EN_CURSO
    assert estado_de_la_base(db) == antes
    assert consultas.pedidos == ["eventos/ca00rr00/video-1790544847"]


def test_si_el_video_ya_termino_se_borra_con_todo(cliente_con_base, cuentas, db, nube,
                                                  monkeypatch):
    """Nadie lo consultó todavía (sigue en `procesando`), pero Cloudinary ya lo
    tiene: está en la carpeta y el borrado por prefijo se lo lleva."""
    evento = con_video_armandose(db, cuentas["organizador"], "Cumple de Juan", "ca00rr00")
    archivos_en_la_nube(nube, evento, fotos=3, videos=0)
    nube.archivos["video"].add("eventos/ca00rr00/video-1790544847")
    monkeypatch.setattr(rutas_admin, "consultar_video", ConsultasDeVideo(url="https://res/v.mp4"))

    r = borrar(cliente_con_base, evento.id, "Cumple de Juan", actor=cuentas["admin"])

    assert r.status_code == 200, r.text
    assert r.json() == {"eliminado": True, "fotos": 3}
    assert nube.archivos == {"image": set(), "video": set()}


def test_un_video_pedido_hace_mas_del_plazo_no_frena_el_borrado(cliente_con_base, cuentas, db,
                                                                nube):
    """Pasado el plazo (30 min) el video se da por fallido, como en armar_video:
    no se le pregunta a Cloudinary (consultar_video está prohibido) y se borra."""
    evento = con_video_armandose(db, cuentas["organizador"], "Cumple de Juan", "ca00rr00",
                                 hace=rutas_admin._PLAZO_VIDEO + timedelta(minutes=1))
    r = borrar(cliente_con_base, evento.id, "Cumple de Juan", actor=cuentas["admin"])
    assert r.status_code == 200, r.text


def test_con_las_fotos_ya_borradas_un_video_que_termino_despues_se_borra_igual(
        cliente_con_base, cuentas, db, nube, monkeypatch):
    """Pedido justo antes de la pasada de los 30 días y terminado después: es el
    único archivo que queda, y sin este borrado quedaría para siempre."""
    evento = con_video_armandose(
        db, cuentas["organizador"], "Egresados 2025", "eg20ve25",
        fotos_borradas_en=datetime.now(timezone.utc) - timedelta(seconds=30),
    )
    nube.archivos["video"].add("eventos/eg20ve25/video-1790544847")
    monkeypatch.setattr(rutas_admin, "consultar_video", ConsultasDeVideo(url="https://res/v.mp4"))

    r = borrar(cliente_con_base, evento.id, "Egresados 2025", actor=cuentas["admin"])

    assert r.status_code == 200, r.text
    assert nube.prefijos() == [("image", "eventos/eg20ve25/"), ("video", "eventos/eg20ve25/")]
    assert nube.archivos["video"] == set()


def test_el_video_se_mira_despues_del_historial_y_del_nombre(cliente_con_base, cuentas, db):
    """El orden: Historial, nombre y recién después el video. Un rechazo de antes
    ni le pregunta a Cloudinary (consultar_video está prohibido)."""
    abierto = con_video_armandose(db, cuentas["organizador"], "Fiesta", "fi00es00",
                                  estado="activo", fecha=HOY)
    terminado = con_video_armandose(db, cuentas["organizador"], "Cumple de Juan", "ca00rr00")
    antes = estado_de_la_base(db)

    r = borrar(cliente_con_base, abierto.id, "Fiesta", actor=cuentas["admin"])
    assert mensaje_de_error(r, "DATOS_INVALIDOS", 422) == SOLO_DEL_HISTORIAL
    r = borrar(cliente_con_base, terminado.id, "Otro nombre", actor=cuentas["admin"])
    assert mensaje_de_error(r, "DATOS_INVALIDOS", 422) == NO_COINCIDE
    assert estado_de_la_base(db) == antes


class VideoQueSeTraba:
    """pedir_video de mentira: el PRIMER pedido se queda esperando hasta `soltar`."""

    def __init__(self) -> None:
        self.adentro = threading.Event()
        self.soltar = threading.Event()
        self.pedidos: list[str] = []

    def __call__(self, codigo: str, public_ids: list[str]) -> str:
        self.pedidos.append(codigo)
        if not self.adentro.is_set():
            self.adentro.set()
            assert self.soltar.wait(15), "nadie soltó el pedido del video"
        return f"eventos/{codigo}/video-{len(self.pedidos)}"


def pedir_el_video(cliente, id_evento: int, actor: Usuario):
    return cliente.post(f"/api/admin/eventos/{id_evento}/video", headers=bearer_de(actor))


def test_si_armar_video_lo_tiene_tomado_el_borrado_espera_y_ve_el_video(
    cliente_con_base, cuentas, eventos, db, motor_prueba, monkeypatch,
):
    """armar_video toma la fila ANTES de pedirle el video a Cloudinary. El
    borrado espera; cuando armar_video guarda `procesando` y suelta, el borrado
    lo ve y responde 422 sin borrar nada (sin `nube`: ni en Cloudinary)."""
    malena = eventos["malena"]
    video = VideoQueSeTraba()
    monkeypatch.setattr(rutas_admin, "pedir_video", video)
    monkeypatch.setattr(rutas_admin, "consultar_video", ConsultasDeVideo(url=None))
    resultados: dict = {}

    armar = en_un_hilo(resultados, "armar", lambda: pedir_el_video(
        cliente_con_base, malena.id, cuentas["organizador"]))
    borrado = None
    try:
        assert video.adentro.wait(15), "armar_video no llegó a Cloudinary"
        borrado = en_un_hilo(resultados, "borrado", lambda: borrar(
            cliente_con_base, malena.id, malena.nombre, actor=cuentas["admin"]))
        esperar_a_que_alguien_espere_un_lock(motor_prueba)
    finally:
        video.soltar.set()
        armar.join(15)
        if borrado is not None:
            borrado.join(15)

    assert resultados["armar"].status_code == 202, resultados["armar"].text
    assert resultados["armar"].json()["estado"] == "procesando"
    assert mensaje_de_error(resultados["borrado"], "DATOS_INVALIDOS", 422) == VIDEO_EN_CURSO
    assert existe(db, malena.id)


def test_si_el_borrado_lo_tiene_tomado_armar_video_espera_y_da_404_sin_pedir_nada(
    cliente_con_base, cuentas, eventos, db, motor_prueba, nube_trabada, monkeypatch,
):
    """Al revés: el borrado tiene el evento y se queda en Cloudinary. armar_video
    espera el lock y, cuando el evento ya no existe, responde 404 SIN pedir el
    video: uno pedido para un evento borrado quedaría en Cloudinary para siempre
    (y el UPDATE de después daba 500)."""
    malena = eventos["malena"]
    archivos_en_la_nube(nube_trabada.nube, malena, fotos=3)
    pedidos: list[str] = []
    monkeypatch.setattr(rutas_admin, "pedir_video",
                        lambda codigo, ids: pedidos.append(codigo) or f"eventos/{codigo}/video-1")
    resultados: dict = {}

    borrado = en_un_hilo(resultados, "borrado", lambda: borrar(
        cliente_con_base, malena.id, malena.nombre, actor=cuentas["admin"]))
    armar = None
    try:
        assert nube_trabada.adentro.wait(15), "el borrado no llegó a Cloudinary"
        armar = en_un_hilo(resultados, "armar", lambda: pedir_el_video(
            cliente_con_base, malena.id, cuentas["organizador"]))
        esperar_a_que_alguien_espere_un_lock(motor_prueba)
    finally:
        nube_trabada.soltar.set()
        borrado.join(15)
        if armar is not None:
            armar.join(15)

    assert resultados["borrado"].status_code == 200, resultados["borrado"].text
    afirmar_error(resultados["armar"], "EVENTO_NO_ENCONTRADO", 404)
    assert pedidos == [], "no se le pidió el video a Cloudinary"


def test_dos_pedidos_de_video_a_la_vez_piden_uno_solo(cliente_con_base, cuentas, eventos,
                                                     motor_prueba, monkeypatch):
    """Con la fila tomada, el segundo pedido (un doble toque) espera, ve el video
    en curso y lo devuelve: Cloudinary recibe un solo pedido."""
    malena = eventos["malena"]
    video = VideoQueSeTraba()
    monkeypatch.setattr(rutas_admin, "pedir_video", video)
    resultados: dict = {}

    primero = en_un_hilo(resultados, "primero", lambda: pedir_el_video(
        cliente_con_base, malena.id, cuentas["admin"]))
    segundo = None
    try:
        assert video.adentro.wait(15)
        segundo = en_un_hilo(resultados, "segundo", lambda: pedir_el_video(
            cliente_con_base, malena.id, cuentas["organizador"]))
        esperar_a_que_alguien_espere_un_lock(motor_prueba)
    finally:
        video.soltar.set()
        primero.join(15)
        if segundo is not None:
            segundo.join(15)

    assert video.pedidos == [malena.codigo_publico]
    for clave in ("primero", "segundo"):
        assert resultados[clave].status_code == 202, resultados[clave].text
        assert resultados[clave].json()["estado"] == "procesando"


@pytest.mark.parametrize("evento,esperado", [("malena", 202), ("de_diego", 404)])
def test_armar_video_sigue_acotando_por_dueno(cliente_con_base, cuentas, eventos, monkeypatch,
                                             evento, esperado):
    """Con la fila tomada, la misma regla que evento_del_usuario: un organizador
    llega a los suyos (malena es de Bruno) y uno ajeno da 404, como uno que no existe."""
    monkeypatch.setattr(rutas_admin, "pedir_video", lambda codigo, ids: f"eventos/{codigo}/video-1")
    r = pedir_el_video(cliente_con_base, eventos[evento].id, cuentas["organizador"])
    assert r.status_code == esperado, r.text
    afirmar_error(pedir_el_video(cliente_con_base, 999999, cuentas["admin"]),
                  "EVENTO_NO_ENCONTRADO", 404)


def test_si_se_borra_mientras_se_consulta_el_video_da_404_y_no_500(
        cliente_con_base, cuentas, db, fabrica, monkeypatch):
    """GET …/video lee el evento sin lock y le pregunta a Cloudinary. Si en el
    medio lo borran, el UPDATE a `listo` no encuentra la fila: 404, no un 500."""
    evento = con_video_armandose(db, cuentas["organizador"], "Cumple de Juan", "ca00rr00")

    def borrarlo_en_el_medio(public_id):
        with fabrica() as otra:
            otra.execute(text("DELETE FROM fotos WHERE evento_id = :id"), {"id": evento.id})
            otra.execute(text("DELETE FROM eventos WHERE id = :id"), {"id": evento.id})
            otra.commit()
        return "https://res/v.mp4"

    monkeypatch.setattr(rutas_admin, "consultar_video", borrarlo_en_el_medio)
    r = cliente_con_base.get(f"/api/admin/eventos/{evento.id}/video",
                             headers=bearer_de(cuentas["admin"]))
    afirmar_error(r, "EVENTO_NO_ENCONTRADO", 404)


# ─────────────────────────────────────────────────────────────
# El log: ids, nunca nombres ni emails
# ─────────────────────────────────────────────────────────────

def test_el_log_lleva_los_ids_y_si_llamo_a_cloudinary(cliente_con_base, cuentas, eventos, db,
                                                      nube, caplog):
    ana, sofia = cuentas["admin"], cuentas["superadmin"]
    malena = eventos["malena"]
    archivos_en_la_nube(nube, malena, fotos=3, videos=1)
    ya_borrado = nuevo_evento(db, cuentas["otro_organizador"], "Egresados 2025", "eg20ve25",
                              fecha=HOY - timedelta(days=45), fotos=2,
                              fotos_borradas_en=datetime(2026, 9, 1, tzinfo=timezone.utc))

    with caplog.at_level(logging.INFO, logger=rutas_admin.log_eventos.name):
        borrar(cliente_con_base, malena.id, malena.nombre, actor=ana)
        borrar(cliente_con_base, ya_borrado.id, ya_borrado.nombre, actor=sofia)

    mensajes = [r.getMessage() for r in caplog.records if r.name == rutas_admin.log_eventos.name]
    assert len(mensajes) == 2, mensajes
    assert all(m.startswith("eventos:") for m in mensajes)
    assert f"cuenta {ana.id}" in mensajes[0] and f"evento {malena.id}" in mensajes[0]
    assert "3 fotos" in mensajes[0] and "4 archivos borrados de Cloudinary" in mensajes[0]
    assert f"cuenta {sofia.id}" in mensajes[1] and f"evento {ya_borrado.id}" in mensajes[1]
    assert "2 fotos" in mensajes[1] and "ya no tenía archivos en Cloudinary" in mensajes[1]
    for dato in ("Malena", "Egresados", "Ana", "Sofía", "Bruno", "@", EMAIL_ORGANIZADOR,
                 EMAIL_SUPERADMIN, malena.codigo_publico, malena.token_pantalla):
        assert dato not in caplog.text


def test_un_rechazo_no_deja_linea_en_el_log(cliente_con_base, cuentas, eventos, caplog):
    with caplog.at_level(logging.INFO, logger=rutas_admin.log_eventos.name):
        borrar(cliente_con_base, eventos["malena"].id, "Otro nombre", actor=cuentas["admin"])
        borrar(cliente_con_base, eventos["malena"].id, "Cumple de 15 de Malena",
               actor=cuentas["organizador"])
        borrar(cliente_con_base, eventos["abierto"].id, "Fiesta que sigue", actor=cuentas["admin"])
        borrar(cliente_con_base, 999999, "Nada", actor=cuentas["admin"])
    assert [r for r in caplog.records if r.name == rutas_admin.log_eventos.name] == []


# ─────────────────────────────────────────────────────────────
# Con un login de verdad, de punta a punta
# ─────────────────────────────────────────────────────────────

def test_de_punta_a_punta_con_login(autorizado, autorizado_organizador, autorizado_superadmin,
                                    cuentas, eventos, db, nube):
    """Bruno (organizador) no puede ni con su evento; Ana (admin) sí, y Sofía
    (superadmin) también, con los tokens del login."""
    malena, de_diego = eventos["malena"], eventos["de_diego"]
    r = autorizado_organizador.request("DELETE", RUTA.format(id=malena.id),
                                       json={"confirmar_nombre": malena.nombre})
    afirmar_error(r, "NO_AUTORIZADO", 403)

    r = autorizado.request("DELETE", RUTA.format(id=malena.id),
                           json={"confirmar_nombre": "cumple de 15 de malena"})
    assert r.status_code == 200 and r.json() == {"eliminado": True, "fotos": 3}

    r = autorizado_superadmin.request("DELETE", RUTA.format(id=de_diego.id),
                                      json={"confirmar_nombre": de_diego.nombre})
    assert r.status_code == 200 and r.json() == {"eliminado": True, "fotos": 2}

    # Bruno sigue viendo su evento futuro, y ya no el que se borró.
    nombres = [e["nombre"] for e in autorizado_organizador.get("/api/admin/eventos").json()]
    assert nombres == ["Casamiento de Bruno"]
