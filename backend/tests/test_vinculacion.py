"""Vinculación de pantalla por código corto.

Es un agregado FUERA del contrato de la sección 5, propuesto y aprobado antes de
escribirlo. Existe porque el link de la pantalla mide 68 caracteres y hay que
poder cargarlo con el control remoto de una tele.

Necesitan Postgres. Definí DATABASE_URL_TEST o se saltean solas.
"""

from __future__ import annotations

import pytest

from app import ratelimit, vinculacion
from tests.conftest import TOKEN_ACTIVO, sin_base

pytestmark = sin_base


@pytest.fixture(autouse=True)
def _sin_codigos_viejos():
    vinculacion.reiniciar()
    yield
    vinculacion.reiniciar()


def afirmar_error(respuesta, codigo_esperado: str, http_esperado: int) -> None:
    assert respuesta.status_code == http_esperado, respuesta.text
    assert respuesta.json()["error"]["codigo"] == codigo_esperado


def generar(autorizado, id_evento: int):
    return autorizado.post(f"/api/admin/eventos/{id_evento}/vincular")


# ─────────────────────────────────────────────────────────────
# Generar el código
# ─────────────────────────────────────────────────────────────

def test_generar_codigo(autorizado, eventos):
    r = generar(autorizado, eventos["activo"].id)
    assert r.status_code == 200, r.text
    assert set(r.json().keys()) == {"codigo", "expira_en"}
    codigo = r.json()["codigo"]
    assert len(codigo) == 6 and codigo.isdigit(), "seis dígitos: el control tiene teclado numérico"


def test_generar_codigo_pide_sesion(cliente_con_base, eventos):
    r = cliente_con_base.post(f"/api/admin/eventos/{eventos['activo'].id}/vincular")
    afirmar_error(r, "NO_AUTORIZADO", 401)


def test_no_se_vincula_un_evento_ajeno(autorizado_organizador, eventos):
    """Los eventos del fixture son de Ana: para Bruno, organizador, son ajenos."""
    afirmar_error(generar(autorizado_organizador, eventos["activo"].id), "EVENTO_NO_ENCONTRADO", 404)


def test_no_se_vincula_un_borrador(autorizado, eventos):
    """Un evento sin publicar no tiene pantalla que mostrar todavía."""
    afirmar_error(generar(autorizado, eventos["borrador"].id), "EVENTO_BORRADOR", 404)


def test_generar_de_nuevo_invalida_el_anterior(autorizado, cliente_con_base, eventos):
    """Dos códigos vivos para la misma pantalla es una puerta abierta de más."""
    primero = generar(autorizado, eventos["activo"].id).json()["codigo"]
    segundo = generar(autorizado, eventos["activo"].id).json()["codigo"]
    assert primero != segundo

    afirmar_error(
        cliente_con_base.post("/api/pantalla/canjear", json={"codigo": primero}),
        "EVENTO_NO_ENCONTRADO", 404,
    )
    assert cliente_con_base.post("/api/pantalla/canjear", json={"codigo": segundo}).status_code == 200


# ─────────────────────────────────────────────────────────────
# Canjear
# ─────────────────────────────────────────────────────────────

def test_canjear_devuelve_el_token_correcto(autorizado, cliente_con_base, eventos):
    codigo = generar(autorizado, eventos["activo"].id).json()["codigo"]
    r = cliente_con_base.post("/api/pantalla/canjear", json={"codigo": codigo})
    assert r.status_code == 200, r.text
    assert set(r.json().keys()) == {"token_pantalla"}
    assert r.json()["token_pantalla"] == TOKEN_ACTIVO


def test_el_token_canjeado_sirve_de_verdad(autorizado, cliente_con_base, eventos):
    """La prueba que importa: con ese token la pantalla ya funciona."""
    codigo = generar(autorizado, eventos["activo"].id).json()["codigo"]
    token = cliente_con_base.post("/api/pantalla/canjear", json={"codigo": codigo}).json()["token_pantalla"]

    config = cliente_con_base.get(f"/api/pantalla/{token}")
    assert config.status_code == 200
    assert config.json()["evento"]["nombre"] == "Casamiento Ana y Juan"

    fotos = cliente_con_base.get(f"/api/pantalla/{token}/fotos?desde=0")
    assert len(fotos.json()["fotos"]) == 6


@pytest.mark.parametrize("escrito", ["{c}", "{c0} {c1}", "{c0}-{c1}"])
def test_se_aceptan_espacios_y_guiones(autorizado, cliente_con_base, eventos, escrito):
    """En la tele el código se muestra separado para leerlo de lejos."""
    codigo = generar(autorizado, eventos["activo"].id).json()["codigo"]
    texto = escrito.format(c=codigo, c0=codigo[:3], c1=codigo[3:])
    r = cliente_con_base.post("/api/pantalla/canjear", json={"codigo": texto})
    assert r.status_code == 200, f"{texto!r} -> {r.text}"


def test_el_codigo_es_de_un_solo_uso(autorizado, cliente_con_base, eventos):
    codigo = generar(autorizado, eventos["activo"].id).json()["codigo"]
    assert cliente_con_base.post("/api/pantalla/canjear", json={"codigo": codigo}).status_code == 200
    afirmar_error(
        cliente_con_base.post("/api/pantalla/canjear", json={"codigo": codigo}),
        "EVENTO_NO_ENCONTRADO", 404,
    )


def test_codigo_inexistente(cliente_con_base, eventos):
    afirmar_error(
        cliente_con_base.post("/api/pantalla/canjear", json={"codigo": "000000"}),
        "EVENTO_NO_ENCONTRADO", 404,
    )


def test_un_codigo_vencido_no_sirve(autorizado, cliente_con_base, eventos, monkeypatch):
    codigo = generar(autorizado, eventos["activo"].id).json()["codigo"]
    # Se adelanta el reloj más allá de la vigencia.
    real = vinculacion._ahora
    monkeypatch.setattr(vinculacion, "_ahora", lambda: real() + vinculacion.VIGENCIA_SEGUNDOS + 1)
    afirmar_error(
        cliente_con_base.post("/api/pantalla/canjear", json={"codigo": codigo}),
        "EVENTO_NO_ENCONTRADO", 404,
    )


def test_el_error_no_distingue_inexistente_de_vencido(autorizado, cliente_con_base, eventos):
    """Distinguirlos le diría a quien prueba al azar cuándo estuvo cerca."""
    codigo = generar(autorizado, eventos["activo"].id).json()["codigo"]
    cliente_con_base.post("/api/pantalla/canjear", json={"codigo": codigo})
    usado = cliente_con_base.post("/api/pantalla/canjear", json={"codigo": codigo})
    inventado = cliente_con_base.post("/api/pantalla/canjear", json={"codigo": "111111"})
    assert usado.json() == inventado.json()


def test_el_canje_tiene_limite_de_pedidos(cliente_con_base, eventos):
    """Es lo que hace que seis dígitos alcancen: sin esto se puede probar al azar."""
    for _ in range(ratelimit.MAXIMO_PEDIDOS):
        cliente_con_base.post("/api/pantalla/canjear", json={"codigo": "123456"})
    afirmar_error(
        cliente_con_base.post("/api/pantalla/canjear", json={"codigo": "123456"}),
        "DEMASIADOS_PEDIDOS", 429,
    )


def test_un_codigo_de_menos_digitos_no_pasa(cliente_con_base, eventos):
    afirmar_error(
        cliente_con_base.post("/api/pantalla/canjear", json={"codigo": "12345"}),
        "DATOS_INVALIDOS", 422,
    )


# ─────────────────────────────────────────────────────────────
# Aislamiento
# ─────────────────────────────────────────────────────────────

def test_cada_evento_canjea_su_propio_token(autorizado, cliente_con_base, eventos):
    codigo_activo = generar(autorizado, eventos["activo"].id).json()["codigo"]
    codigo_cerrado = generar(autorizado, eventos["cerrado"].id).json()["codigo"]

    t1 = cliente_con_base.post("/api/pantalla/canjear", json={"codigo": codigo_activo}).json()
    t2 = cliente_con_base.post("/api/pantalla/canjear", json={"codigo": codigo_cerrado}).json()

    assert t1["token_pantalla"] != t2["token_pantalla"]
    assert t1["token_pantalla"] == TOKEN_ACTIVO
