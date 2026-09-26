"""El día del borrado, aunque la pasada de limpieza todavía no haya corrido.

A los 30 días de la fecha del evento se borran sus fotos y videos de
Cloudinary (test_limpieza.py). La pasada corre en cualquier momento de ese día:
en Render gratuito, un minuto después de que alguien despierta la API, que
suele ser la organizadora entrando a descargar. Por eso desde ese DÍA, y no
desde que la pasada marca el evento, nada ofrece ni sirve los archivos. Y si
igual falta una foto, el ZIP lo dice adentro.

También: no se crea un evento con una fecha que ya nacería vencida, y el
arranque deja dicho en el log si la limpieza quedó andando.

"Hoy" se fija siempre con monkeypatch sobre `limpieza.hoy_en_argentina`, que
es el único reloj del borrado: estas pruebas no dependen del día en que corren.
"""

from __future__ import annotations

import io
import logging
import zipfile
from datetime import date, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import cloudinary_service as cs
from app import limpieza
from app.main import app
from app.models import Evento
from app.routers import admin as rutas_admin
from tests.conftest import TOKEN_ACTIVO, TOKEN_CERRADO, sin_base

# Los eventos del fixture `eventos` son del 12/9/2026: se borran el 12/10.
DIA_DEL_BORRADO = date(2026, 10, 12)
LA_VISPERA = DIA_DEL_BORRADO - timedelta(days=1)

SE_ESTAN_BORRANDO = "Las fotos y el video de este evento se están borrando"
URL_VIDEO = "https://res.cloudinary.com/nube/video/upload/v1/eventos/ab12cd34/video-1.mp4"


def fijar_hoy(monkeypatch, dia: date) -> None:
    monkeypatch.setattr(limpieza, "hoy_en_argentina", lambda: dia)


def afirmar_error(respuesta, codigo: str, http: int) -> dict:
    assert respuesta.status_code == http, respuesta.text
    cuerpo = respuesta.json()
    assert set(cuerpo) == {"error"} and cuerpo["error"]["codigo"] == codigo
    return cuerpo["error"]


@pytest.fixture()
def sin_cloudinary(monkeypatch):
    """Nada de estas pruebas puede llegar a Cloudinary: ni el ZIP ni el video."""

    def prohibido(*_a, **_k):
        raise AssertionError("se intentó usar los archivos de un evento vencido")

    monkeypatch.setattr(rutas_admin, "armar_zip", prohibido)
    monkeypatch.setattr(rutas_admin, "consultar_video", prohibido)
    monkeypatch.setattr(rutas_admin, "pedir_video", prohibido)


# ─────────────────────────────────────────────────────────────
# El criterio, sin base
# ─────────────────────────────────────────────────────────────

def test_vence_el_dia_30_de_la_fecha():
    fecha = date(2026, 9, 12)
    assert not limpieza.fecha_vencida(fecha, LA_VISPERA)
    assert limpieza.fecha_vencida(fecha, DIA_DEL_BORRADO)
    assert limpieza.fecha_vencida(fecha, DIA_DEL_BORRADO + timedelta(days=200))


def test_es_el_mismo_corte_que_la_pasada():
    """`fecha_vencida` y `eventos_vencidos` no pueden discrepar ni un día: si
    no, habría un día sin descarga y sin borrado, o con los dos a la vez."""
    hoy = date(2026, 10, 12)
    for atras in range(25, 36):
        fecha = hoy - timedelta(days=atras)
        assert limpieza.fecha_vencida(fecha, hoy) is (
            fecha <= hoy - timedelta(days=limpieza.DIAS_HASTA_BORRAR)
        )


def test_el_hoy_sale_de_la_limpieza(monkeypatch):
    fijar_hoy(monkeypatch, LA_VISPERA)
    assert not limpieza.fecha_vencida(date(2026, 9, 12))
    fijar_hoy(monkeypatch, DIA_DEL_BORRADO)
    assert limpieza.fecha_vencida(date(2026, 9, 12))


def test_archivos_vencidos_por_fecha_o_por_marca():
    from datetime import datetime, timezone

    sin_marca = Evento(fecha_evento=date(2026, 9, 12), fotos_borradas_en=None)
    assert not limpieza.archivos_vencidos(sin_marca, LA_VISPERA)
    assert limpieza.archivos_vencidos(sin_marca, DIA_DEL_BORRADO), "la pasada todavía no corrió"

    marcado = Evento(fecha_evento=date(2026, 9, 12),
                     fotos_borradas_en=datetime(2026, 10, 12, 3, tzinfo=timezone.utc))
    assert limpieza.archivos_vencidos(marcado, LA_VISPERA), "con la marca, siempre"


# ─────────────────────────────────────────────────────────────
# El día del borrado, antes de que pase la limpieza
# ─────────────────────────────────────────────────────────────

@sin_base
def test_el_dia_del_borrado_no_se_descarga_ni_se_arma_video(autorizado, eventos, sin_cloudinary,
                                                            monkeypatch, db):
    """El caso del hallazgo: la organizadora entra el día X, la API se despierta
    y la pasada va a borrar en un minuto. La descarga no arranca."""
    fijar_hoy(monkeypatch, DIA_DEL_BORRADO)
    for id_evento in (eventos["activo"].id, eventos["cerrado"].id):
        assert db.get(Evento, id_evento).fotos_borradas_en is None, "la pasada no corrió"
        for respuesta in (
            autorizado.get(f"/api/admin/eventos/{id_evento}/descarga"),
            autorizado.get(f"/api/admin/eventos/{id_evento}/descarga?incluir=todas"),
            autorizado.get(f"/api/admin/eventos/{id_evento}/video"),
            autorizado.post(f"/api/admin/eventos/{id_evento}/video"),
        ):
            error = afirmar_error(respuesta, "DATOS_INVALIDOS", 410)
            assert error["mensaje"] == SE_ESTAN_BORRANDO


@sin_base
def test_la_vispera_se_descarga(autorizado, eventos, monkeypatch):
    fijar_hoy(monkeypatch, LA_VISPERA)
    monkeypatch.setattr(rutas_admin, "armar_zip", lambda fotos: iter([b"zip"]))
    r = autorizado.get(f"/api/admin/eventos/{eventos['activo'].id}/descarga")
    assert r.status_code == 200, r.text
    assert r.content == b"zip"


@sin_base
def test_el_dia_del_borrado_la_pantalla_no_recibe_fotos(cliente_con_base, eventos, monkeypatch):
    fijar_hoy(monkeypatch, LA_VISPERA)
    assert len(cliente_con_base.get(f"/api/pantalla/{TOKEN_ACTIVO}/fotos").json()["fotos"]) == 6
    assert cliente_con_base.get(f"/api/pantalla/{TOKEN_ACTIVO}").json()["evento"]["estado"] == "activo"

    fijar_hoy(monkeypatch, DIA_DEL_BORRADO)
    for token in (TOKEN_ACTIVO, TOKEN_CERRADO):
        assert cliente_con_base.get(f"/api/pantalla/{token}/fotos?desde=0").json() == {
            "fotos": [], "ultimo_id": 0,
        }
        assert cliente_con_base.get(f"/api/pantalla/{token}/fotos?desde=7").json() == {
            "fotos": [], "ultimo_id": 7,
        }
        config = cliente_con_base.get(f"/api/pantalla/{token}").json()
        assert config["evento"]["estado"] == "cerrado", "muestra el cierre, no el QR"


@sin_base
def test_el_dia_del_borrado_no_se_ofrece_el_video(autorizado, eventos, db, monkeypatch):
    activo = db.get(Evento, eventos["activo"].id)
    activo.video_estado, activo.video_url = "listo", URL_VIDEO
    db.commit()

    fijar_hoy(monkeypatch, LA_VISPERA)
    filas = {e["id"]: e for e in autorizado.get("/api/admin/eventos").json()}
    assert filas[activo.id]["video_url_listo"] == URL_VIDEO

    fijar_hoy(monkeypatch, DIA_DEL_BORRADO)
    filas = {e["id"]: e for e in autorizado.get("/api/admin/eventos").json()}
    assert filas[activo.id]["video_url_listo"] is None
    assert filas[activo.id]["fotos_borradas_en"] is None, "la marca la pone sólo la pasada"
    assert filas[activo.id]["fotos_se_borran_el"] == DIA_DEL_BORRADO.isoformat()


@sin_base
def test_el_dia_del_borrado_no_se_reabre_pero_se_cierra(autorizado, eventos, monkeypatch):
    fijar_hoy(monkeypatch, DIA_DEL_BORRADO)
    id_cerrado = eventos["cerrado"].id
    for estado in ("activo", "borrador"):
        error = afirmar_error(
            autorizado.patch(f"/api/admin/eventos/{id_cerrado}", json={"estado": estado}),
            "DATOS_INVALIDOS", 409,
        )
        assert error["mensaje"] == "Las fotos de este evento se están borrando: no se puede reabrir"

    r = autorizado.patch(f"/api/admin/eventos/{eventos['activo'].id}", json={"estado": "cerrado"})
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "cerrado"

    fijar_hoy(monkeypatch, LA_VISPERA)
    r = autorizado.patch(f"/api/admin/eventos/{id_cerrado}", json={"estado": "activo"})
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "activo"


# ─────────────────────────────────────────────────────────────
# Crear un evento con una fecha que ya nacería vencida
# ─────────────────────────────────────────────────────────────

HOY = date(2026, 9, 26)


def cuantos_eventos(db) -> int:
    db.expire_all()
    return db.scalar(select(func.count()).select_from(Evento))


@sin_base
@pytest.mark.parametrize("fecha", [
    HOY - timedelta(days=30),        # se borraría hoy mismo
    HOY - timedelta(days=400),
    date(2025, 9, 26),               # el año mal puesto
])
def test_no_se_crea_un_evento_ya_vencido(autorizado, db, monkeypatch, fecha):
    fijar_hoy(monkeypatch, HOY)
    antes = cuantos_eventos(db)
    error = afirmar_error(
        autorizado.post("/api/admin/eventos", json={"nombre": "Casamiento", "fecha_evento": fecha.isoformat()}),
        "DATOS_INVALIDOS", 422,
    )
    assert error["mensaje"] == "Esa fecha ya pasó hace 30 días o más. Revisá el año"
    assert cuantos_eventos(db) == antes, "no quedó nada a medio crear"


@sin_base
@pytest.mark.parametrize("atras", [29, 1, 0, -1, -400])
def test_una_fecha_de_hace_menos_de_30_dias_se_crea(autorizado, monkeypatch, atras):
    """Para juntar las fotos de una fiesta que ya pasó. La de hace 29 días se
    borra mañana, y el panel lo avisa."""
    fijar_hoy(monkeypatch, HOY)
    fecha = HOY - timedelta(days=atras)
    r = autorizado.post("/api/admin/eventos", json={"nombre": "Cumple", "fecha_evento": fecha.isoformat()})
    assert r.status_code == 201, r.text
    assert r.json()["fotos_se_borran_el"] == (fecha + timedelta(days=30)).isoformat()


@sin_base
def test_un_organizador_tampoco_crea_uno_vencido(autorizado_organizador, monkeypatch):
    fijar_hoy(monkeypatch, HOY)
    afirmar_error(
        autorizado_organizador.post("/api/admin/eventos",
                                    json={"nombre": "Viejo", "fecha_evento": "2025-09-26"}),
        "DATOS_INVALIDOS", 422,
    )


# ─────────────────────────────────────────────────────────────
# El ZIP dice adentro si le faltan fotos
# ─────────────────────────────────────────────────────────────

JPEG = b"\xff\xd8\xff\xe0" + b"x" * 5000


class CorteAMitad(httpx.SyncByteStream):
    """Una respuesta que manda un pedazo y se corta."""

    def __iter__(self):
        yield JPEG[:1000]
        raise httpx.ReadError("se cortó la red")


def nube_de_fotos(monkeypatch, respuestas: dict[str, object]) -> None:
    """Cada URL responde lo que diga `respuestas`: un código HTTP, una
    excepción, o CorteAMitad. Lo que no está, 200 con un JPEG."""
    cliente_real = httpx.Client

    def responder(pedido: httpx.Request) -> httpx.Response:
        que = respuestas.get(str(pedido.url), 200)
        if isinstance(que, Exception):
            raise que
        if que is CorteAMitad:
            return httpx.Response(200, stream=CorteAMitad())
        return httpx.Response(que, content=JPEG if que == 200 else b"no")

    monkeypatch.setattr(
        httpx, "Client", lambda **k: cliente_real(transport=httpx.MockTransport(responder), **k)
    )


def abrir(fotos) -> zipfile.ZipFile:
    z = zipfile.ZipFile(io.BytesIO(b"".join(cs.armar_zip(fotos))))
    assert z.testzip() is None, "el ZIP está sano"
    return z


def url(n: int) -> str:
    return f"https://res.cloudinary.com/demo/image/upload/v1/eventos/ab12cd34/f{n}.jpg"


def test_completo_no_lleva_aviso(monkeypatch):
    nube_de_fotos(monkeypatch, {})
    z = abrir([("Ana", url(1)), ("Juan", url(2))])
    assert z.namelist() == ["001 - Ana.jpg", "002 - Juan.jpg"]


def test_si_falta_una_lo_dice_y_cual(monkeypatch):
    nube_de_fotos(monkeypatch, {url(2): 404})
    z = abrir([("Ana", url(1)), ("Juan", url(2)), ("Lu", url(3))])
    assert z.namelist() == ["001 - Ana.jpg", "003 - Lu.jpg", cs.NOMBRE_FALTANTES]
    texto = z.read(cs.NOMBRE_FALTANTES).decode("utf-8")
    assert texto.startswith("No se pudo bajar 1 de las 3 fotos.")
    assert "002 - Juan.jpg" in texto


def test_si_cloudinary_ya_no_tiene_ninguna_el_zip_no_parece_completo(monkeypatch):
    """El ZIP vacío que salía con 200 y sin ningún aviso."""
    nube_de_fotos(monkeypatch, {url(1): 404, url(2): 404})
    z = abrir([("Ana", url(1)), ("Juan", url(2))])
    assert z.namelist() == [cs.NOMBRE_FALTANTES]
    texto = z.read(cs.NOMBRE_FALTANTES).decode("utf-8")
    assert texto.startswith("No se pudo bajar ninguna de las 2 fotos.")


def test_sin_red_o_cortada_a_mitad(monkeypatch):
    nube_de_fotos(monkeypatch, {
        url(1): httpx.ConnectError("sin red"),
        url(2): CorteAMitad,
    })
    z = abrir([("Ana", url(1)), ("Juan", url(2)), ("Lu", url(3))])
    assert z.namelist() == ["002 - Juan.jpg", "003 - Lu.jpg", cs.NOMBRE_FALTANTES]
    assert len(z.read("002 - Juan.jpg")) < len(JPEG), "está, pero cortada"
    texto = z.read(cs.NOMBRE_FALTANTES).decode("utf-8")
    assert texto.startswith("No se pudieron bajar 2 de las 3 fotos.")
    no_estan, cortadas = texto.split("Están, pero quedaron cortadas:")
    assert "001 - Ana.jpg" in no_estan and "002 - Juan.jpg" in cortadas


def test_una_sola_foto():
    assert cs.texto_faltantes(["001.jpg"], [], 1).startswith("No se pudo bajar la foto.")


def test_el_aviso_va_primero_al_abrir_la_carpeta():
    assert sorted([cs.NOMBRE_FALTANTES, "001 - Ana.jpg", "001.jpg"])[0] == cs.NOMBRE_FALTANTES


# ─────────────────────────────────────────────────────────────
# El arranque dice si la limpieza quedó andando
# ─────────────────────────────────────────────────────────────

def mensajes_de_limpieza(caplog) -> list[tuple[int, str]]:
    return [(r.levelno, r.getMessage()) for r in caplog.records if r.name == limpieza.log.name]


def test_el_arranque_dice_limpieza_activa(monkeypatch, caplog):
    # Sin las tres credenciales no corre aunque se la pida (config.py).
    monkeypatch.setattr(cs.config, "CLOUDINARY_CLOUD_NAME", "nube-falsa")
    monkeypatch.setattr(cs.config, "CLOUDINARY_API_KEY", "clave-falsa")
    monkeypatch.setattr(cs.config, "CLOUDINARY_API_SECRET", "secreto-falso")
    monkeypatch.setattr(cs.config, "LIMPIEZA_ACTIVA", True)
    monkeypatch.setattr(limpieza, "ESPERA_INICIAL_S", 60.0)  # la pasada no llega a correr
    monkeypatch.setattr(limpieza, "pasada_de_limpieza", lambda: 0)
    with caplog.at_level(logging.INFO, logger=limpieza.log.name):
        with TestClient(app):
            pass
    [(nivel, mensaje)] = mensajes_de_limpieza(caplog)
    assert nivel == logging.INFO
    assert mensaje.startswith("limpieza: activa"), "en Render se busca por «limpieza»"
    assert "30 días" in mensaje


def test_apagada_en_produccion_avisa(monkeypatch, caplog):
    monkeypatch.setattr(cs.config, "ENTORNO", "produccion")
    monkeypatch.setattr(cs.config, "LIMPIEZA_ACTIVA", False)
    with caplog.at_level(logging.INFO, logger=limpieza.log.name):
        with TestClient(app):
            pass
    [(nivel, mensaje)] = mensajes_de_limpieza(caplog)
    assert nivel == logging.WARNING
    assert mensaje.startswith("limpieza: APAGADA")


def test_apagada_en_desarrollo_no_dice_nada(monkeypatch, caplog):
    monkeypatch.setattr(cs.config, "ENTORNO", "desarrollo")
    monkeypatch.setattr(cs.config, "LIMPIEZA_ACTIVA", False)
    with caplog.at_level(logging.INFO, logger=limpieza.log.name):
        with TestClient(app):
            pass
    assert mensajes_de_limpieza(caplog) == []
