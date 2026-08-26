"""Verifica que cada endpoint devuelve la forma EXACTA de la sección 5.

Acá van sólo las pruebas que NO necesitan base: los endpoints públicos y de
pantalla (que todavía responden datos fijos), la forma de los errores y la
superficie de la API. Las de administración, que desde la Fase 2 consultan
la base de verdad, viven en test_fase2.py.

No comprueba valores (en la Fase 1 son inventados): comprueba el conjunto de
claves de cada respuesta y el formato de los errores. Si alguien agrega, saca o
renombra un campo, estas pruebas fallan. Es a propósito: el contrato es lo que
permite construir las tres interfaces en paralelo.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app

CODIGO_ACTIVO = "ab12cd34"
CODIGO_CERRADO = "ef56gh78"
TOKEN_ACTIVO = "64syPN4YFgbJibLfIOlrjI51R0HFlKDm"


@pytest.fixture(scope="module")
def cliente() -> TestClient:
    return TestClient(app)


def claves(respuesta) -> set[str]:
    return set(respuesta.json().keys())


# ─────────────────────────────────────────────────────────────
# Forma del error
# ─────────────────────────────────────────────────────────────

def afirmar_error(respuesta, codigo_esperado: str, http_esperado: int) -> None:
    assert respuesta.status_code == http_esperado, respuesta.text
    cuerpo = respuesta.json()
    assert set(cuerpo.keys()) == {"error"}
    assert set(cuerpo["error"].keys()) == {"codigo", "mensaje"}
    assert cuerpo["error"]["codigo"] == codigo_esperado
    assert isinstance(cuerpo["error"]["mensaje"], str) and cuerpo["error"]["mensaje"]


# ─────────────────────────────────────────────────────────────
# Públicos
# ─────────────────────────────────────────────────────────────

def test_evento_publico(cliente):
    r = cliente.get(f"/api/e/{CODIGO_ACTIVO}")
    assert r.status_code == 200
    assert claves(r) == {"nombre", "fecha_evento", "estado", "max_fotos_por_dispositivo"}
    assert "id" not in r.json(), "regla 1: el id interno no sale en respuestas públicas"


def test_evento_publico_cerrado_sigue_respondiendo(cliente):
    r = cliente.get(f"/api/e/{CODIGO_CERRADO}")
    assert r.status_code == 200
    assert r.json()["estado"] == "cerrado"


def test_evento_publico_inexistente(cliente):
    afirmar_error(cliente.get("/api/e/noexiste"), "EVENTO_NO_ENCONTRADO", 404)


def test_firma(cliente):
    r = cliente.post(f"/api/e/{CODIGO_ACTIVO}/firma", json={"dispositivo_hash": "9f2c1a7b4e8d0c35"})
    assert r.status_code == 200
    assert claves(r) == {"cloud_name", "api_key", "timestamp", "signature", "folder"}
    assert r.json()["folder"] == f"eventos/{CODIGO_ACTIVO}"


def test_firma_evento_cerrado(cliente):
    r = cliente.post(f"/api/e/{CODIGO_CERRADO}/firma", json={"dispositivo_hash": "9f2c1a7b4e8d0c35"})
    afirmar_error(r, "EVENTO_CERRADO", 409)


def test_firma_cuerpo_invalido(cliente):
    afirmar_error(cliente.post(f"/api/e/{CODIGO_ACTIVO}/firma", json={}), "DATOS_INVALIDOS", 422)


def _foto(codigo: str = CODIGO_ACTIVO) -> dict:
    return {
        "public_id": f"eventos/{codigo}/k3j2h1",
        "url": "https://res.cloudinary.com/demo/image/upload/v1/x.jpg",
        "ancho": 1600,
        "alto": 1200,
        "bytes": 348211,
        "dispositivo_hash": "9f2c1a7b4e8d0c35",
        "nombre_invitado": "Sofi",
    }


def test_registrar_foto(cliente):
    r = cliente.post(f"/api/e/{CODIGO_ACTIVO}/fotos", json=_foto())
    assert r.status_code == 201
    assert claves(r) == {"id", "estado"}


def test_registrar_foto_public_id_ajeno(cliente):
    """Regla 4: sin esta verificación se puede proyectar cualquier imagen."""
    cuerpo = _foto()
    cuerpo["public_id"] = "eventos/otroevento/k3j2h1"
    afirmar_error(cliente.post(f"/api/e/{CODIGO_ACTIVO}/fotos", json=cuerpo), "PUBLIC_ID_AJENO", 403)


def test_registrar_foto_evento_cerrado(cliente):
    r = cliente.post(f"/api/e/{CODIGO_CERRADO}/fotos", json=_foto(CODIGO_CERRADO))
    afirmar_error(r, "EVENTO_CERRADO", 409)


# ─────────────────────────────────────────────────────────────
# Pantalla
# ─────────────────────────────────────────────────────────────

def test_pantalla(cliente):
    r = cliente.get(f"/api/pantalla/{TOKEN_ACTIVO}")
    assert r.status_code == 200
    cuerpo = r.json()
    assert set(cuerpo.keys()) == {"evento", "config"}
    assert set(cuerpo["evento"].keys()) == {"nombre", "codigo_publico", "estado"}
    assert set(cuerpo["config"].keys()) == {
        "segundos_por_foto", "intervalo_polling_ms", "maximo_buffer"
    }
    assert "id" not in cuerpo["evento"], "regla 1"


def test_pantalla_token_inexistente(cliente):
    afirmar_error(cliente.get("/api/pantalla/noexiste"), "EVENTO_NO_ENCONTRADO", 404)


def test_pantalla_arranque_en_frio(cliente):
    """desde=0 devuelve las últimas `limite`, de la más vieja a la más nueva."""
    r = cliente.get(f"/api/pantalla/{TOKEN_ACTIVO}/fotos?desde=0&limite=40")
    assert r.status_code == 200
    cuerpo = r.json()
    assert set(cuerpo.keys()) == {"fotos", "ultimo_id"}
    assert set(cuerpo["fotos"][0].keys()) == {"id", "url", "ancho", "alto", "nombre_invitado"}
    ids = [f["id"] for f in cuerpo["fotos"]]
    assert ids == sorted(ids), "tienen que venir ascendentes"
    assert cuerpo["ultimo_id"] == ids[-1]


def test_pantalla_polling_incremental(cliente):
    """desde=N devuelve sólo las de id > N."""
    todas = cliente.get(f"/api/pantalla/{TOKEN_ACTIVO}/fotos?desde=0").json()["fotos"]
    corte = todas[len(todas) // 2]["id"]
    cuerpo = cliente.get(f"/api/pantalla/{TOKEN_ACTIVO}/fotos?desde={corte}").json()
    assert all(f["id"] > corte for f in cuerpo["fotos"])
    assert cuerpo["ultimo_id"] == todas[-1]["id"]


def test_pantalla_sin_novedades_devuelve_el_desde_recibido(cliente):
    cuerpo = cliente.get(f"/api/pantalla/{TOKEN_ACTIVO}/fotos?desde=99999").json()
    assert cuerpo["fotos"] == []
    assert cuerpo["ultimo_id"] == 99999


def test_pantalla_limite(cliente):
    cuerpo = cliente.get(f"/api/pantalla/{TOKEN_ACTIVO}/fotos?desde=0&limite=3").json()
    assert len(cuerpo["fotos"]) == 3


# ─────────────────────────────────────────────────────────────
# Administración
# ─────────────────────────────────────────────────────────────

RUTAS_PROTEGIDAS = [
    ("get", "/api/admin/eventos"),
    ("post", "/api/admin/eventos"),
    ("patch", "/api/admin/eventos/1"),
    ("get", "/api/admin/eventos/1/fotos"),
    ("get", "/api/admin/eventos/1/resumen"),
    ("patch", "/api/admin/fotos/1"),
    ("post", "/api/admin/fotos/lote"),
    ("get", "/api/admin/eventos/1/descarga"),
]


@pytest.mark.parametrize("metodo,ruta", RUTAS_PROTEGIDAS)
def test_sin_bearer_es_no_autorizado(cliente, metodo, ruta):
    afirmar_error(getattr(cliente, metodo)(ruta), "NO_AUTORIZADO", 401)


# ─────────────────────────────────────────────────────────────
# Salud y superficie total
# ─────────────────────────────────────────────────────────────

def test_salud_sin_auth(cliente):
    r = cliente.get("/api/salud")
    assert r.status_code == 200
    assert claves(r) == {"estado", "base"}


def test_ruta_inexistente_respeta_el_contrato(cliente):
    r = cliente.get("/api/no-existe")
    assert r.status_code == 404
    assert set(r.json().keys()) == {"error"}


def test_los_catorce_endpoints_del_contrato(cliente):
    """14 endpoints del contrato + /api/salud, que el brief marca aparte.

    Se mira el esquema OpenAPI, que es exactamente lo que lista /docs.
    """
    esquema = cliente.get("/openapi.json").json()
    rutas = {
        (metodo.upper(), ruta)
        for ruta, operaciones in esquema["paths"].items()
        for metodo in operaciones
        if ruta.startswith("/api")
    }
    del_contrato = sorted(x for x in rutas if x[1] != "/api/salud")
    assert len(del_contrato) == 14, del_contrato
    assert ("GET", "/api/salud") in rutas

    assert del_contrato == [
        ("GET", "/api/admin/eventos"),
        ("GET", "/api/admin/eventos/{id_evento}/descarga"),
        ("GET", "/api/admin/eventos/{id_evento}/fotos"),
        ("GET", "/api/admin/eventos/{id_evento}/resumen"),
        ("GET", "/api/e/{codigo_publico}"),
        ("GET", "/api/pantalla/{token_pantalla}"),
        ("GET", "/api/pantalla/{token_pantalla}/fotos"),
        ("PATCH", "/api/admin/eventos/{id_evento}"),
        ("PATCH", "/api/admin/fotos/{id_foto}"),
        ("POST", "/api/admin/eventos"),
        ("POST", "/api/admin/fotos/lote"),
        ("POST", "/api/admin/login"),
        ("POST", "/api/e/{codigo_publico}/firma"),
        ("POST", "/api/e/{codigo_publico}/fotos"),
    ]


def test_los_errores_estan_documentados_en_docs(cliente):
    """El criterio pide la forma exacta del contrato «incluidos los errores»."""
    esquema = cliente.get("/openapi.json").json()
    sin_errores = [
        f"{m.upper()} {ruta}"
        for ruta, operaciones in esquema["paths"].items()
        if ruta.startswith("/api") and ruta != "/api/salud"
        for m, op in operaciones.items()
        if not [c for c in op.get("responses", {}) if c.startswith(("4", "5"))]
    ]
    assert sin_errores == [], sin_errores
