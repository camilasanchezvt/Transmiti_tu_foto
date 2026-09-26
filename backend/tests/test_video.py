"""Video del evento: lo que se le pide a Cloudinary, sin llamarlo de verdad."""

from __future__ import annotations

import hashlib
import json

import httpx
import pytest

from app import cloudinary_service as cs
from tests.conftest import sin_base
from tests.test_fase4 import afirmar_error


def test_si_entran_van_todas_en_orden():
    ids = [f"eventos/ab/f{i}" for i in range(5)]
    assert cs.elegir_fotos_para_video(ids, tope=10) == ids


def test_si_sobran_se_reparten_de_punta_a_punta():
    ids = [str(i) for i in range(100)]
    elegidas = cs.elegir_fotos_para_video(ids, tope=5)
    assert elegidas == ["0", "25", "50", "74", "99"]
    assert elegidas[0] == "0" and elegidas[-1] == "99", "la primera y la última de la noche"


def test_manifiesto():
    m = json.loads(cs.manifiesto_video(["eventos/ab/x1", "eventos/ab/x2"]))
    assert m["w"] == cs.VIDEO_ANCHO and m["h"] == cs.VIDEO_ALTO
    assert m["du"] == 6
    assert m["vars"]["slides"] == [{"media": "i:eventos/ab/x1"}, {"media": "i:eventos/ab/x2"}]


def test_pedido_firmado(monkeypatch):
    enviado = {}

    def falso_post(url, data, timeout):
        enviado.update(url=url, data=data)
        return httpx.Response(200, json={"status": "processing"})

    monkeypatch.setattr(httpx, "post", falso_post)
    monkeypatch.setattr(cs.config, "CLOUDINARY_API_SECRET", "secreto")
    monkeypatch.setattr(cs.config, "CLOUDINARY_CLOUD_NAME", "nube")

    public_id = cs.pedir_video("ab12", ["eventos/ab12/f1"], momento=1700000000)

    assert public_id == "eventos/ab12/video-1700000000", "dentro de la carpeta del evento"
    assert enviado["url"].endswith("/nube/video/create_slideshow")
    datos = enviado["data"]
    esperado = hashlib.sha1(
        (
            f"manifest_json={datos['manifest_json']}&public_id={public_id}&timestamp=1700000000"
            + "secreto"
        ).encode()
    ).hexdigest()
    assert datos["signature"] == esperado
    assert "secreto" not in json.dumps(datos), "el secreto nunca viaja"


def test_pedido_rechazado_levanta_error(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *a, **k: httpx.Response(400, text="nope"))
    with pytest.raises(cs.ErrorVideo):
        cs.pedir_video("ab12", ["eventos/ab12/f1"])


def test_consultar_video(monkeypatch):
    monkeypatch.setattr(
        httpx, "get", lambda *a, **k: httpx.Response(200, json={"secure_url": "https://res/v.mp4"})
    )
    assert cs.consultar_video("eventos/ab/video-1") == "https://res/v.mp4"
    monkeypatch.setattr(httpx, "get", lambda *a, **k: httpx.Response(404, json={}))
    assert cs.consultar_video("eventos/ab/video-1") is None


# ─────────────────────────────────────────────────────────────
# Endpoints, con base
# ─────────────────────────────────────────────────────────────

@sin_base
def test_sin_aprobadas_no_se_arma(autorizado, eventos, db, monkeypatch):
    from app.models import Foto
    from sqlalchemy import update

    db.execute(update(Foto).where(Foto.evento_id == eventos["activo"].id).values(estado="pendiente"))
    db.commit()
    afirmar_error(
        autorizado.post(f"/api/admin/eventos/{eventos['activo'].id}/video"), "DATOS_INVALIDOS", 422
    )


@sin_base
def test_armar_y_consultar(autorizado, eventos, monkeypatch):
    from app.routers import admin as rutas

    pedidos = []
    monkeypatch.setattr(rutas, "pedir_video", lambda codigo, ids: pedidos.append(ids) or "eventos/x/video-1")
    monkeypatch.setattr(rutas, "consultar_video", lambda pid: None)

    id_evento = eventos["activo"].id
    assert autorizado.get(f"/api/admin/eventos/{id_evento}/video").json()["estado"] == "ninguno"

    r = autorizado.post(f"/api/admin/eventos/{id_evento}/video")
    assert r.status_code == 202
    assert r.json()["estado"] == "procesando"
    assert r.json()["fotos"] == 6

    autorizado.post(f"/api/admin/eventos/{id_evento}/video")
    assert len(pedidos) == 1, "un segundo clic no pide otro video"

    monkeypatch.setattr(rutas, "consultar_video", lambda pid: "https://res.cloudinary.com/v.mp4")
    listo = autorizado.get(f"/api/admin/eventos/{id_evento}/video").json()
    assert listo == {**listo, "estado": "listo", "url": "https://res.cloudinary.com/v.mp4"}


@sin_base
def test_si_cloudinary_rechaza_queda_en_fallo(autorizado, eventos, monkeypatch):
    from app.routers import admin as rutas

    def rechaza(codigo, ids):
        raise cs.ErrorVideo("400")

    monkeypatch.setattr(rutas, "pedir_video", rechaza)
    r = autorizado.post(f"/api/admin/eventos/{eventos['activo'].id}/video")
    assert r.json()["estado"] == "fallo"
