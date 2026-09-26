"""Borrado automático de Cloudinary a los 30 días de la fecha del evento.

Cloudinary está SIEMPRE simulado: un fixture automático reemplaza httpx.delete
por uno que falla si alguna prueba se olvida de poner su propia nube falsa.
Ningún pedido sale de verdad.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import Counter
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from app import cloudinary_service as cs
from app import limpieza
from app.config import Config
from app.main import app
from app.models import Evento, Foto, Usuario
from tests.conftest import (
    CODIGO_ACTIVO,
    CODIGO_CERRADO,
    EMAIL_ADMIN,
    TOKEN_ACTIVO,
    sin_base,
)

SECRETO = "secreto-de-prueba-que-no-sale"
NUBE = "nube-falsa"
CLAVE = "clave-falsa"

# La fecha de los eventos del fixture `eventos` es el 12/9/2026: se borran el 12/10.
VENCE_EL_FIXTURE = date(2026, 10, 12)


@pytest.fixture(autouse=True)
def _cloudinary_simulado(monkeypatch):
    """Credenciales de mentira y ningún DELETE de verdad."""

    def prohibido(*_a, **_k):
        raise AssertionError("una prueba intentó borrar en Cloudinary de verdad")

    monkeypatch.setattr(httpx, "delete", prohibido)
    monkeypatch.setattr(cs.config, "CLOUDINARY_CLOUD_NAME", NUBE)
    monkeypatch.setattr(cs.config, "CLOUDINARY_API_KEY", CLAVE)
    monkeypatch.setattr(cs.config, "CLOUDINARY_API_SECRET", SECRETO)


class NubeFalsa:
    """Un Cloudinary de mentira que borra por prefijo como el de verdad: de a
    `por_pedido` archivos, y avisando con `next_cursor` y `partial` si quedan.

    `falla(tipo, params)` puede devolver una respuesta o una excepción para
    simular errores; si devuelve None, el pedido anda.
    """

    def __init__(self, image=(), video=(), por_pedido=1000):
        self.archivos = {"image": set(image), "video": set(video)}
        self.por_pedido = por_pedido
        self.pedidos: list[dict] = []
        self.falla = None

    def delete(self, url, *, params=None, auth=None, timeout=None, **_):
        tipo = url.split("/resources/")[1].split("/")[0]
        self.pedidos.append({"url": url, "tipo": tipo, "params": dict(params), "auth": auth})
        if self.falla is not None:
            resultado = self.falla(tipo, params)
            if isinstance(resultado, Exception):
                raise resultado
            if resultado is not None:
                return resultado
        prefijo = params["prefix"]
        tanda = sorted(p for p in self.archivos[tipo] if p.startswith(prefijo))[: self.por_pedido]
        self.archivos[tipo] -= set(tanda)
        quedan = any(p.startswith(prefijo) for p in self.archivos[tipo])
        cuerpo = {"deleted": {p: "deleted" for p in tanda}, "partial": quedan}
        if quedan:
            cuerpo["next_cursor"] = f"cursor-{len(self.pedidos)}"
        return httpx.Response(200, json=cuerpo)

    def prefijos(self) -> list[tuple[str, str]]:
        return [(p["tipo"], p["params"]["prefix"]) for p in self.pedidos]


@pytest.fixture()
def nube(monkeypatch) -> NubeFalsa:
    falsa = NubeFalsa()
    monkeypatch.setattr(httpx, "delete", falsa.delete)
    return falsa


# ─────────────────────────────────────────────────────────────
# Fecha y prefijo, sin base
# ─────────────────────────────────────────────────────────────

def test_se_borran_a_los_30_dias_de_la_fecha():
    assert limpieza.fotos_se_borran_el(date(2026, 9, 12)) == date(2026, 10, 12)
    assert limpieza.fotos_se_borran_el(date(2026, 12, 15)) == date(2027, 1, 14)
    assert limpieza.fotos_se_borran_el(date(2028, 2, 10)) == date(2028, 3, 11), "año bisiesto"


def test_el_prefijo_lleva_la_barra_final():
    assert cs.prefijo_del_evento("ab12cd34") == "eventos/ab12cd34/"


@pytest.mark.parametrize("codigo", ["", "ab/12", "..", "ab 12", "ab12/", "*"])
def test_un_codigo_raro_no_pide_ningun_borrado(codigo, nube):
    with pytest.raises(cs.ErrorBorrado):
        cs.borrar_archivos_del_evento(codigo)
    assert nube.pedidos == []


def test_el_evento_ab12_no_borra_los_archivos_de_ab123(nube):
    nube.archivos["image"] = {"eventos/ab12/f1", "eventos/ab12/f2", "eventos/ab123/f1"}
    nube.archivos["video"] = {"eventos/ab12/video-1", "eventos/ab123/video-2"}

    borrados = cs.borrar_archivos_del_evento("ab12")

    assert borrados == 3
    assert nube.archivos == {"image": {"eventos/ab123/f1"}, "video": {"eventos/ab123/video-2"}}
    assert nube.prefijos() == [("image", "eventos/ab12/"), ("video", "eventos/ab12/")]


def test_el_pedido_es_el_de_la_admin_api(nube):
    cs.borrar_archivos_del_evento("ab12cd34")

    assert [p["url"] for p in nube.pedidos] == [
        f"https://api.cloudinary.com/v1_1/{NUBE}/resources/image/upload",
        f"https://api.cloudinary.com/v1_1/{NUBE}/resources/video/upload",
    ]
    for pedido in nube.pedidos:
        assert pedido["auth"] == (CLAVE, SECRETO), "basic auth, como consultar_video"
        assert pedido["params"]["invalidate"] == "true", "que la CDN deje de servirlas"
        assert SECRETO not in str(pedido["params"]), "el secreto no va en la URL"


def test_pagina_con_next_cursor_hasta_terminar(nube):
    nube.por_pedido = 2
    nube.archivos["image"] = {f"eventos/ab12/f{i}" for i in range(5)}

    assert cs.borrar_por_prefijo("eventos/ab12/", "image") == 5

    cursores = [p["params"].get("next_cursor") for p in nube.pedidos]
    assert cursores == [None, "cursor-1", "cursor-2"], "cada vuelta manda el cursor de la anterior"
    assert nube.archivos["image"] == set()
    assert all(p["params"]["invalidate"] == "true" for p in nube.pedidos)


def test_partial_sin_cursor_vuelve_a_pedir(monkeypatch):
    respuestas = iter([
        httpx.Response(200, json={"deleted": {"a": "deleted"}, "partial": True}),
        httpx.Response(200, json={"deleted": {"b": "deleted", "c": "not_found"}, "partial": False}),
    ])
    pedidos = []
    monkeypatch.setattr(httpx, "delete", lambda url, **k: pedidos.append(k["params"]) or next(respuestas))

    assert cs.borrar_por_prefijo("eventos/ab12/", "image") == 2, "not_found no cuenta"
    assert len(pedidos) == 2
    assert "next_cursor" not in pedidos[1]


def test_si_nunca_termina_corta_y_levanta(monkeypatch):
    monkeypatch.setattr(cs, "MAXIMO_VUELTAS_BORRADO", 3)
    pedidos = []
    monkeypatch.setattr(
        httpx, "delete",
        lambda url, **k: pedidos.append(1) or httpx.Response(200, json={"partial": True, "next_cursor": "x"}),
    )
    with pytest.raises(cs.ErrorBorrado):
        cs.borrar_por_prefijo("eventos/ab12/", "image")
    assert len(pedidos) == 3


@pytest.mark.parametrize(
    "falla",
    [
        httpx.Response(500, text="error interno"),
        httpx.Response(420, text="Rate Limit Exceeded"),
        httpx.Response(401, text="Invalid api_key"),
        httpx.ConnectError("sin red"),
        httpx.ReadTimeout("tarde"),
        httpx.Response(200, text="<html>no es json</html>"),
    ],
)
def test_un_error_de_cloudinary_levanta_error_de_borrado(falla, nube):
    nube.falla = lambda tipo, params: falla
    with pytest.raises(cs.ErrorBorrado) as info:
        cs.borrar_archivos_del_evento("ab12cd34")
    assert SECRETO not in str(info.value)


# ─────────────────────────────────────────────────────────────
# La pasada de limpieza, con base
# ─────────────────────────────────────────────────────────────

@pytest.fixture()
def fabrica(motor_prueba):
    return sessionmaker(bind=motor_prueba, autoflush=False, expire_on_commit=False)


def nuevo_evento(db, codigo: str, fecha: date, estado: str = "cerrado", **extra) -> Evento:
    dueno = extra.pop("usuario", None) or db.scalar(select(Usuario).where(Usuario.email == EMAIL_ADMIN))
    evento = Evento(
        usuario_id=dueno.id,
        nombre=f"Evento {codigo}",
        fecha_evento=fecha,
        codigo_publico=codigo,
        token_pantalla=f"T{codigo}".ljust(32, "x"),
        estado=estado,
        **extra,
    )
    db.add(evento)
    db.commit()
    return evento


def releer(db, evento: Evento) -> Evento:
    db.expire_all()
    return db.get(Evento, evento.id)


@sin_base
def test_vencidos_el_dia_30_si_el_29_no(limpiar, fabrica, nube):
    db = limpiar
    hoy = date(2026, 10, 12)
    dia_29 = nuevo_evento(db, "dia29aa", hoy - timedelta(days=29))
    dia_30 = nuevo_evento(db, "dia30aa", hoy - timedelta(days=30))
    dia_31 = nuevo_evento(db, "dia31aa", hoy - timedelta(days=31))
    nuevo_evento(db, "yaborra", hoy - timedelta(days=90),
                 fotos_borradas_en=datetime(2026, 8, 1, tzinfo=timezone.utc))

    with fabrica() as s:
        assert [e.codigo_publico for e in limpieza.eventos_vencidos(s, hoy)] == ["dia31aa", "dia30aa"]

    assert limpieza.pasada_de_limpieza(hoy=hoy, fabrica_de_sesiones=fabrica) == 2
    assert {prefijo for _, prefijo in nube.prefijos()} == {"eventos/dia31aa/", "eventos/dia30aa/"}
    assert releer(db, dia_29).fotos_borradas_en is None
    assert releer(db, dia_30).fotos_borradas_en is not None
    assert releer(db, dia_31).fotos_borradas_en is not None

    # Al día siguiente le toca al que ayer iba por el día 29.
    assert limpieza.pasada_de_limpieza(hoy=hoy + timedelta(days=1), fabrica_de_sesiones=fabrica) == 1
    assert nube.prefijos()[-2:] == [("image", "eventos/dia29aa/"), ("video", "eventos/dia29aa/")]
    assert releer(db, dia_29).fotos_borradas_en is not None


@sin_base
def test_hoy_por_defecto_es_el_de_argentina(limpiar, fabrica, nube, monkeypatch):
    db = limpiar
    ayer_en_argentina = date(2026, 10, 11)
    nuevo_evento(db, "vence12", date(2026, 9, 12))
    monkeypatch.setattr(limpieza, "hoy_en_argentina", lambda: ayer_en_argentina)
    assert limpieza.pasada_de_limpieza(fabrica_de_sesiones=fabrica) == 0
    monkeypatch.setattr(limpieza, "hoy_en_argentina", lambda: VENCE_EL_FIXTURE)
    assert limpieza.pasada_de_limpieza(fabrica_de_sesiones=fabrica) == 1


@sin_base
def test_borra_imagenes_y_videos_y_cierra_lo_que_seguia_abierto(limpiar, fabrica, nube):
    db = limpiar
    fecha = date(2026, 9, 1)
    cerrado_antes = datetime(2026, 9, 2, 3, 0, tzinfo=timezone.utc)
    abierto = nuevo_evento(db, "abierto", fecha, "activo",
                           video_estado="listo", video_url="https://res/v.mp4")
    sin_publicar = nuevo_evento(db, "borrado", fecha, "borrador")
    cerrado = nuevo_evento(db, "cerrado", fecha, "cerrado", cerrado_en=cerrado_antes)
    nube.archivos["image"] = {"eventos/abierto/f1", "eventos/abierto/f2", "eventos/cerrado/f1"}
    nube.archivos["video"] = {"eventos/abierto/video-1", "eventos/abierto/video-2"}

    antes = datetime.now(timezone.utc)
    assert limpieza.pasada_de_limpieza(hoy=date(2026, 10, 1), fabrica_de_sesiones=fabrica) == 3
    despues = datetime.now(timezone.utc)

    assert nube.archivos == {"image": set(), "video": set()}, "fotos y todos los videos"
    abierto, sin_publicar, cerrado = (releer(db, e) for e in (abierto, sin_publicar, cerrado))
    for e in (abierto, sin_publicar, cerrado):
        assert antes <= e.fotos_borradas_en <= despues
        assert e.estado == "cerrado"
    assert abierto.cerrado_en == abierto.fotos_borradas_en, "se cierra en el mismo momento"
    assert sin_publicar.cerrado_en == sin_publicar.fotos_borradas_en
    assert cerrado.cerrado_en == cerrado_antes, "el que ya estaba cerrado conserva su fecha"
    assert (abierto.video_estado, abierto.video_url) == ("listo", "https://res/v.mp4"), (
        "el video queda como estaba: el que deja de ofrecerlo es el panel"
    )


@sin_base
def test_las_filas_no_se_borran(eventos, db, fabrica, nube):
    fotos_antes = db.scalar(select(func.count()).select_from(Foto))
    eventos_antes = db.scalar(select(func.count()).select_from(Evento))

    assert limpieza.pasada_de_limpieza(hoy=VENCE_EL_FIXTURE, fabrica_de_sesiones=fabrica) == 3

    db.expire_all()
    assert db.scalar(select(func.count()).select_from(Foto)) == fotos_antes == 11
    assert db.scalar(select(func.count()).select_from(Evento)) == eventos_antes


@sin_base
def test_correr_dos_veces_no_vuelve_a_llamar_a_cloudinary(limpiar, fabrica, nube):
    nuevo_evento(limpiar, "unavez1", date(2026, 8, 1))
    assert limpieza.pasada_de_limpieza(hoy=date(2026, 10, 1), fabrica_de_sesiones=fabrica) == 1
    pedidos = len(nube.pedidos)
    assert pedidos == 2

    assert limpieza.pasada_de_limpieza(hoy=date(2026, 10, 1), fabrica_de_sesiones=fabrica) == 0
    assert limpieza.pasada_de_limpieza(hoy=date(2027, 1, 1), fabrica_de_sesiones=fabrica) == 0
    assert len(nube.pedidos) == pedidos


@sin_base
def test_si_cloudinary_falla_a_mitad_no_se_marca_y_se_reintenta(limpiar, fabrica, nube, caplog):
    db = limpiar
    hoy = date(2026, 10, 1)
    falla = nuevo_evento(db, "fallaaa", date(2026, 8, 1), "activo")
    anda = nuevo_evento(db, "andaaaa", date(2026, 8, 2))
    nube.archivos["image"] = {"eventos/fallaaa/f1"}
    nube.archivos["video"] = {"eventos/fallaaa/video-1"}

    # Las imágenes de `fallaaa` salen, el video no: quedó a medio borrar.
    def video_de_fallaaa(tipo, params):
        if tipo == "video" and params["prefix"] == "eventos/fallaaa/":
            return httpx.Response(500, text="Cloudinary está caído")
        return None

    nube.falla = video_de_fallaaa
    with caplog.at_level(logging.ERROR, logger=limpieza.log.name):
        assert limpieza.pasada_de_limpieza(hoy=hoy, fabrica_de_sesiones=fabrica) == 1

    falla = releer(db, falla)
    assert falla.fotos_borradas_en is None, "no se marca: se reintenta"
    assert (falla.estado, falla.cerrado_en) == ("activo", None), "tampoco se cierra"
    assert releer(db, anda).fotos_borradas_en is not None, "uno que falla no frena a los demás"
    assert "se reintenta" in caplog.text and "500" in caplog.text
    assert SECRETO not in caplog.text and CLAVE not in caplog.text

    # En la pasada siguiente Cloudinary anda: se vuelve a pedir todo y se marca.
    nube.falla = None
    antes = len(nube.pedidos)
    assert limpieza.pasada_de_limpieza(hoy=hoy, fabrica_de_sesiones=fabrica) == 1
    assert nube.prefijos()[antes:] == [("image", "eventos/fallaaa/"), ("video", "eventos/fallaaa/")]
    assert nube.archivos == {"image": set(), "video": set()}
    falla = releer(db, falla)
    assert falla.fotos_borradas_en is not None and falla.estado == "cerrado"


@sin_base
def test_sin_red_no_se_marca(limpiar, fabrica, nube):
    evento = nuevo_evento(limpiar, "sinredd", date(2026, 8, 1))
    nube.falla = lambda tipo, params: httpx.ConnectError("sin red")
    assert limpieza.pasada_de_limpieza(hoy=date(2026, 10, 1), fabrica_de_sesiones=fabrica) == 0
    assert len(nube.pedidos) == 1, "no sigue con los videos si las fotos fallaron"
    assert releer(limpiar, evento).fotos_borradas_en is None


def test_con_la_base_caida_no_levanta(caplog):
    def base_caida():
        raise OperationalError("SELECT 1", None, Exception("Supabase pausado"))

    with caplog.at_level(logging.ERROR, logger=limpieza.log.name):
        assert limpieza.pasada_de_limpieza(hoy=date(2026, 10, 1), fabrica_de_sesiones=base_caida) == 0
    assert "la pasada se cortó" in caplog.text


@sin_base
def test_dos_pasadas_a_la_vez_no_borran_dos_veces(limpiar, fabrica, monkeypatch):
    """La pasada A se queda trabada en Cloudinary con el primer evento tomado.
    Mientras, la pasada B lo saltea (SKIP LOCKED) y se encarga del segundo.
    Cuando A sigue, el segundo ya está marcado. Cada carpeta se pide una vez."""
    hoy = date(2026, 10, 1)
    nuevo_evento(limpiar, "primero", date(2026, 8, 1))
    nuevo_evento(limpiar, "segundo", date(2026, 8, 2))

    pedidos: list[tuple[str, str, str]] = []
    a_adentro = threading.Event()
    soltar_a = threading.Event()

    def delete_lento(url, *, params=None, **_):
        hilo = threading.current_thread().name
        pedidos.append((hilo, url.split("/resources/")[1].split("/")[0], params["prefix"]))
        if hilo == "pasada-a" and not a_adentro.is_set():
            a_adentro.set()
            assert soltar_a.wait(15)
        return httpx.Response(200, json={"deleted": {}, "partial": False})

    monkeypatch.setattr(httpx, "delete", delete_lento)

    resultados: dict[str, int] = {}
    hilo_a = threading.Thread(
        target=lambda: resultados.__setitem__("a", limpieza.pasada_de_limpieza(hoy, fabrica)),
        name="pasada-a",
    )
    hilo_a.start()
    try:
        assert a_adentro.wait(15), "la pasada A no llegó a Cloudinary"
        resultados["b"] = limpieza.pasada_de_limpieza(hoy, fabrica)
    finally:
        soltar_a.set()
        hilo_a.join(15)

    assert resultados == {"a": 1, "b": 1}
    por_carpeta = Counter((tipo, prefijo) for _, tipo, prefijo in pedidos)
    assert por_carpeta == {
        ("image", "eventos/primero/"): 1, ("video", "eventos/primero/"): 1,
        ("image", "eventos/segundo/"): 1, ("video", "eventos/segundo/"): 1,
    }
    assert {p for h, _, p in pedidos if h == "pasada-a"} == {"eventos/primero/"}
    with fabrica() as s:
        assert s.scalar(select(func.count()).select_from(Evento)
                        .where(Evento.fotos_borradas_en.is_(None))) == 0


@sin_base
def test_un_evento_tomado_no_frena_el_alta_de_una_foto(limpiar, fabrica):
    """El lock es FOR NO KEY UPDATE: una foto nueva del mismo evento (que sólo
    necesita la clave, por la clave foránea) no se queda esperando."""
    evento = nuevo_evento(limpiar, "tomadoo", date(2026, 8, 1), "activo")
    with fabrica() as pasada, fabrica() as invitado:
        assert [e.id for e in limpieza.eventos_vencidos(pasada, date(2026, 10, 1))] == [evento.id]
        invitado.execute(text("SET LOCAL lock_timeout = '2s'"))
        invitado.add(Foto(evento_id=evento.id, public_id="eventos/tomadoo/f1",
                          url="https://res.cloudinary.com/demo/image/upload/eventos/tomadoo/f1.jpg"))
        invitado.commit()
        pasada.rollback()


# ─────────────────────────────────────────────────────────────
# Los endpoints después del borrado
# ─────────────────────────────────────────────────────────────

@pytest.fixture()
def borrados(eventos, fabrica, nube):
    """Los tres eventos del fixture, con los archivos ya borrados."""
    assert limpieza.pasada_de_limpieza(hoy=VENCE_EL_FIXTURE, fabrica_de_sesiones=fabrica) == 3
    return eventos


def afirmar_error(respuesta, codigo: str, http: int) -> dict:
    assert respuesta.status_code == http, respuesta.text
    cuerpo = respuesta.json()
    assert set(cuerpo) == {"error"} and cuerpo["error"]["codigo"] == codigo
    return cuerpo["error"]


@sin_base
def test_la_pantalla_no_recibe_fotos(cliente_con_base, borrados):
    assert cliente_con_base.get(f"/api/pantalla/{TOKEN_ACTIVO}/fotos?desde=0").json() == {
        "fotos": [], "ultimo_id": 0,
    }
    assert cliente_con_base.get(f"/api/pantalla/{TOKEN_ACTIVO}/fotos?desde=5").json() == {
        "fotos": [], "ultimo_id": 5,
    }
    config = cliente_con_base.get(f"/api/pantalla/{TOKEN_ACTIVO}").json()
    assert config["evento"]["estado"] == "cerrado"


@sin_base
def test_el_invitado_encuentra_el_evento_cerrado(cliente_con_base, borrados):
    assert cliente_con_base.get(f"/api/e/{CODIGO_ACTIVO}").json()["estado"] == "cerrado"
    afirmar_error(
        cliente_con_base.post(f"/api/e/{CODIGO_ACTIVO}/firma", json={"dispositivo_hash": "f" * 32}),
        "EVENTO_CERRADO", 409,
    )
    foto = {
        "public_id": f"eventos/{CODIGO_ACTIVO}/nueva1", "ancho": 10, "alto": 10, "bytes": 10,
        "url": f"https://res.cloudinary.com/demo/image/upload/v1/eventos/{CODIGO_ACTIVO}/nueva1.jpg",
        "dispositivo_hash": "f" * 32,
    }
    afirmar_error(cliente_con_base.post(f"/api/e/{CODIGO_ACTIVO}/fotos", json=foto), "EVENTO_CERRADO", 409)


@sin_base
def test_con_las_fotos_borradas_no_se_sube_aunque_figure_abierto(cliente_con_base, eventos, db):
    """Si alguien lo reabriera a mano en la base, igual no entra nada."""
    evento = db.get(Evento, eventos["activo"].id)
    evento.fotos_borradas_en = datetime.now(timezone.utc)
    db.commit()
    afirmar_error(
        cliente_con_base.post(f"/api/e/{CODIGO_ACTIVO}/firma", json={"dispositivo_hash": "f" * 32}),
        "EVENTO_CERRADO", 409,
    )


@sin_base
def test_descarga_y_video_responden_410(autorizado, borrados):
    for id_evento in (borrados["activo"].id, borrados["cerrado"].id):
        for respuesta in (
            autorizado.get(f"/api/admin/eventos/{id_evento}/descarga"),
            autorizado.get(f"/api/admin/eventos/{id_evento}/descarga?incluir=todas"),
            autorizado.get(f"/api/admin/eventos/{id_evento}/video"),
            autorizado.post(f"/api/admin/eventos/{id_evento}/video"),
        ):
            error = afirmar_error(respuesta, "DATOS_INVALIDOS", 410)
            assert error["mensaje"] == "Las fotos y el video de este evento ya se borraron"


@sin_base
def test_revisar_sigue_teniendo_las_filas(autorizado, borrados):
    id_evento = borrados["activo"].id
    fotos = autorizado.get(f"/api/admin/eventos/{id_evento}/fotos?limite=200").json()["fotos"]
    assert len(fotos) == 9, "las filas quedan; el panel decide no mostrarlas"
    assert autorizado.get(f"/api/admin/eventos/{id_evento}/resumen").json() == {
        "pendientes": 2, "aprobadas": 6, "rechazadas": 1,
    }


@sin_base
def test_no_se_reabre_un_evento_con_las_fotos_borradas(autorizado, borrados):
    id_evento = borrados["activo"].id
    for estado in ("activo", "borrador"):
        afirmar_error(
            autorizado.patch(f"/api/admin/eventos/{id_evento}", json={"estado": estado}),
            "DATOS_INVALIDOS", 409,
        )
    # Lo demás se puede tocar, y volver a mandar `cerrado` no es un error.
    r = autorizado.patch(f"/api/admin/eventos/{id_evento}",
                         json={"estado": "cerrado", "segundos_por_foto": 9})
    assert r.status_code == 200, r.text
    assert (r.json()["estado"], r.json()["segundos_por_foto"]) == ("cerrado", 9)


@sin_base
def test_uno_borrado_que_figura_abierto_se_puede_cerrar(autorizado, eventos, db):
    """Si quedara abierto por algún camino (un UPDATE a mano), cerrarlo sí se puede."""
    evento = db.get(Evento, eventos["activo"].id)
    evento.fotos_borradas_en = datetime.now(timezone.utc)
    db.commit()
    r = autorizado.patch(f"/api/admin/eventos/{evento.id}", json={"estado": "cerrado"})
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "cerrado"


# ─────────────────────────────────────────────────────────────
# Los campos nuevos de EventoAdmin
# ─────────────────────────────────────────────────────────────

@sin_base
def test_eventoadmin_para_un_admin(autorizado, eventos, db, fabrica, nube):
    activo = db.get(Evento, eventos["activo"].id)
    activo.video_estado, activo.video_url = "listo", "https://res.cloudinary.com/nube/video/upload/v1/eventos/ab12cd34/video-1.mp4"
    cerrado = db.get(Evento, eventos["cerrado"].id)
    cerrado.video_estado, cerrado.video_url = "procesando", None
    db.commit()

    filas = {e["codigo_publico"]: e for e in autorizado.get("/api/admin/eventos").json()}
    for e in filas.values():
        assert e["fotos_se_borran_el"] == "2026-10-12"
        assert e["fotos_borradas_en"] is None
    assert filas[CODIGO_ACTIVO]["video_url_listo"] == activo.video_url
    assert filas[CODIGO_CERRADO]["video_url_listo"] is None, "procesando no es listo"

    # Un video que terminó mal no se ofrece aunque haya quedado una URL vieja.
    activo = db.get(Evento, activo.id)
    activo.video_estado = "fallo"
    db.commit()
    un_evento = autorizado.patch(f"/api/admin/eventos/{activo.id}", json={"segundos_por_foto": 8}).json()
    assert un_evento["video_url_listo"] is None
    assert un_evento["fotos_se_borran_el"] == "2026-10-12"

    activo = db.get(Evento, activo.id)
    activo.video_estado = "listo"
    db.commit()
    assert limpieza.pasada_de_limpieza(hoy=VENCE_EL_FIXTURE, fabrica_de_sesiones=fabrica) == 3

    for e in autorizado.get("/api/admin/eventos?alcance=historial").json():
        borradas = datetime.fromisoformat(e["fotos_borradas_en"])
        assert borradas.tzinfo is not None, "timestamptz, con zona"
        assert e["video_url_listo"] is None, "con los archivos borrados no hay video que ofrecer"
        assert e["estado"] == "cerrado"


@sin_base
def test_eventoadmin_para_un_organizador(autorizado_organizador, organizador, db, fabrica, nube):
    r = autorizado_organizador.post(
        "/api/admin/eventos", json={"nombre": "Cumple de Bruno", "fecha_evento": "2026-12-15"}
    )
    assert r.status_code == 201, r.text
    creado = r.json()
    assert (creado["fotos_se_borran_el"], creado["fotos_borradas_en"], creado["video_url_listo"]) == (
        "2027-01-14", None, None,
    )

    evento = db.get(Evento, creado["id"])
    evento.video_estado, evento.video_url = "listo", "https://res.cloudinary.com/nube/video/upload/v1/x.mp4"
    db.commit()
    [fila] = autorizado_organizador.get("/api/admin/eventos").json()
    assert fila["video_url_listo"] == "https://res.cloudinary.com/nube/video/upload/v1/x.mp4"

    assert limpieza.pasada_de_limpieza(hoy=date(2027, 1, 13), fabrica_de_sesiones=fabrica) == 0
    assert limpieza.pasada_de_limpieza(hoy=date(2027, 1, 14), fabrica_de_sesiones=fabrica) == 1

    [fila] = autorizado_organizador.get("/api/admin/eventos").json()
    assert fila["fotos_borradas_en"] is not None and fila["video_url_listo"] is None
    afirmar_error(autorizado_organizador.get(f"/api/admin/eventos/{creado['id']}/video"),
                  "DATOS_INVALIDOS", 410)


# ─────────────────────────────────────────────────────────────
# Configuración y tarea en segundo plano
# ─────────────────────────────────────────────────────────────

def _config(**valores) -> Config:
    base = {
        "ENTORNO": "desarrollo",
        "JWT_SECRET": "j" * 48,
        "CLOUDINARY_CLOUD_NAME": NUBE,
        "CLOUDINARY_API_KEY": CLAVE,
        "CLOUDINARY_API_SECRET": SECRETO,
    }
    return Config(**{**base, **valores})


def test_la_limpieza_corre_sola_solo_en_produccion(monkeypatch):
    monkeypatch.delenv("LIMPIEZA_ACTIVA", raising=False)
    assert _config().limpieza_activa is False, "en desarrollo, no"
    assert _config(ENTORNO="produccion").limpieza_activa is True
    assert _config(ENTORNO="produccion", LIMPIEZA_ACTIVA=False).limpieza_activa is False
    assert _config(LIMPIEZA_ACTIVA=True).limpieza_activa is True, "forzada en desarrollo"


def test_sin_credenciales_de_cloudinary_no_corre(monkeypatch):
    monkeypatch.delenv("LIMPIEZA_ACTIVA", raising=False)
    assert _config(LIMPIEZA_ACTIVA=True, CLOUDINARY_API_SECRET="").limpieza_activa is False
    assert _config(LIMPIEZA_ACTIVA=True, CLOUDINARY_API_KEY="").limpieza_activa is False
    assert _config(LIMPIEZA_ACTIVA=True, CLOUDINARY_CLOUD_NAME="").limpieza_activa is False


def test_en_las_pruebas_esta_apagada():
    from app.config import obtener_config

    assert obtener_config().LIMPIEZA_ACTIVA is False
    assert obtener_config().limpieza_activa is False


def _activar(monkeypatch, espera: float, intervalo: float) -> None:
    monkeypatch.setattr(cs.config, "LIMPIEZA_ACTIVA", True)
    monkeypatch.setattr(limpieza, "ESPERA_INICIAL_S", espera)
    monkeypatch.setattr(limpieza, "INTERVALO_S", intervalo)


def test_el_arranque_no_espera_a_la_primera_pasada(monkeypatch):
    """Con la espera de verdad (60 s), la app arranca y se apaga en el acto, y
    la pasada no llega a correr: el health check de Render no la espera."""
    corridas = []
    _activar(monkeypatch, espera=60.0, intervalo=6 * 3600.0)
    monkeypatch.setattr(limpieza, "pasada_de_limpieza", lambda: corridas.append(1) or 0)

    inicio = time.monotonic()
    with TestClient(app):
        assert time.monotonic() - inicio < 5
    assert time.monotonic() - inicio < 10, "al apagar, la tarea se cancela y no se la espera"
    assert corridas == []


def test_corre_en_un_thread_se_repite_y_sobrevive_a_un_error(monkeypatch):
    corridas: list[bool] = []
    listo = threading.Event()
    _activar(monkeypatch, espera=0.01, intervalo=0.01)

    def pasada_falsa():
        try:
            asyncio.get_running_loop()
            en_el_loop = True
        except RuntimeError:
            en_el_loop = False
        corridas.append(en_el_loop)
        if len(corridas) == 1:
            raise RuntimeError("una pasada que revienta igual")
        if len(corridas) >= 3:
            listo.set()
        return 0

    monkeypatch.setattr(limpieza, "pasada_de_limpieza", pasada_falsa)
    with TestClient(app):
        assert listo.wait(5), f"el bucle no siguió después del error: {corridas}"
    assert corridas and not any(corridas), "la pasada corre fuera del loop de eventos"


def test_apagada_no_agenda_nada(monkeypatch):
    corridas = []
    monkeypatch.setattr(limpieza, "ESPERA_INICIAL_S", 0.0)
    monkeypatch.setattr(limpieza, "pasada_de_limpieza", lambda: corridas.append(1) or 0)
    with TestClient(app):
        time.sleep(0.2)
    assert corridas == []
