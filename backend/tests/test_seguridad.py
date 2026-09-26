"""Topes de pedidos y validaciones que frenan abusos.

Lo que se prueba acá, en el orden del archivo:

- La IP de los topes: nunca el primer valor de X-Forwarded-For, que lo escribe
  el cliente. Con uno inventado por pedido se evadían todos los topes.
- La limpieza del límite en memoria no recorre el diccionario en cada pedido.
- verificar_url exige la forma exacta de la URL de Cloudinary.
- Login con tope por IP y por email.
- Registro de fotos con tope por celular y por conexión, y con largo máximo.

Las que necesitan Postgres llevan @sin_base y se saltean sin DATABASE_URL_TEST.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from starlette.requests import Request

from app import ratelimit
from app.cloudinary_service import verificar_public_id, verificar_url
from app.errores import ErrorApp
from app.main import app
from app.models import Foto
from app.routers import admin as rutas_admin
from app.routers import cuentas as rutas_cuentas
from app.routers import publico as rutas_publico
from tests.conftest import CODIGO_ACTIVO, EMAIL_ADMIN, PASSWORD_ADMIN, sin_base, url_de

DISPOSITIVO = "5eg0r1d4d0000000000000000000000a"


def afirmar_error(respuesta, codigo_esperado: str, http_esperado: int) -> None:
    assert respuesta.status_code == http_esperado, respuesta.text
    cuerpo = respuesta.json()
    assert set(cuerpo.keys()) == {"error"}
    assert cuerpo["error"]["codigo"] == codigo_esperado


def pedido_con(cabeceras: dict[str, str], cliente: str = "10.0.0.1") -> Request:
    """Un Request de Starlette armado a mano, sin servidor."""
    return Request({
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(k.lower().encode(), v.encode()) for k, v in cabeceras.items()],
        "client": (cliente, 50000),
    })


def detras_del_proxy(ip_real: str, inventada: str) -> dict[str, str]:
    """Lo que llega cuando el cliente manda su propio X-Forwarded-For: el proxy
    agrega la IP real AL FINAL, sin borrar lo que venía."""
    return {"X-Forwarded-For": f"{inventada}, {ip_real}"}


# ─────────────────────────────────────────────────────────────
# La IP de los topes
# ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "cabeceras,esperada",
    [
        ({}, "10.0.0.1"),
        ({"X-Forwarded-For": "203.0.113.7"}, "203.0.113.7"),
        ({"X-Forwarded-For": "inventada, 203.0.113.50"}, "203.0.113.50"),
        ({"X-Forwarded-For": "1.1.1.1, 2.2.2.2 , 203.0.113.50 "}, "203.0.113.50"),
        ({"X-Forwarded-For": " , "}, "10.0.0.1"),
        ({"CF-Connecting-IP": "198.51.100.4", "X-Forwarded-For": "otra, 203.0.113.50"},
         "198.51.100.4"),
    ],
)
def test_la_ip_nunca_es_el_primer_valor_que_manda_el_cliente(cabeceras, esperada):
    assert ratelimit.ip_del_pedido(pedido_con(cabeceras)) == esperada


def test_una_sola_funcion_de_ip_para_todos():
    """Había tres copias, y las tres tomaban el primer valor."""
    from app.routers import cuentas, pantalla, publico

    for modulo in (cuentas, pantalla, publico, rutas_admin):
        assert not hasattr(modulo, "_ip_del_pedido"), modulo.__name__
        assert modulo.ip_del_pedido is ratelimit.ip_del_pedido


@pytest.fixture()
def cliente_sin_base():
    """El canje de pantalla no toca la base: se puede probar sin Postgres."""
    with TestClient(app) as c:
        yield c


def canjear(cliente, cabeceras: dict[str, str]):
    return cliente.post("/api/pantalla/canjear", json={"codigo": "123456"}, headers=cabeceras)


def test_inventar_x_forwarded_for_no_evade_el_tope_del_canje(cliente_sin_base):
    """El caso más grave: sin tope, el código de 6 dígitos se prueba por fuerza
    bruta y se consigue el token de la pantalla de un evento ajeno."""
    for i in range(ratelimit.MAXIMO_PEDIDOS):
        r = canjear(cliente_sin_base, detras_del_proxy("203.0.113.50", f"10.9.{i}.1"))
        afirmar_error(r, "EVENTO_NO_ENCONTRADO", 404)
    r = canjear(cliente_sin_base, detras_del_proxy("203.0.113.50", "otra-mas"))
    afirmar_error(r, "DEMASIADOS_PEDIDOS", 429)
    assert len(ratelimit._pedidos) == 1, "una sola cuenta: la IP real, no una por IP inventada"

    otra = canjear(cliente_sin_base, detras_del_proxy("198.51.100.9", "10.9.0.1"))
    afirmar_error(otra, "EVENTO_NO_ENCONTRADO", 404)


def test_con_cloudflare_cuenta_su_cabecera_y_no_la_del_cliente(cliente_sin_base):
    for i in range(ratelimit.MAXIMO_PEDIDOS):
        canjear(cliente_sin_base, {"CF-Connecting-IP": "198.51.100.4",
                                   "X-Forwarded-For": f"10.8.{i}.1, 10.7.{i}.1"})
    r = canjear(cliente_sin_base, {"CF-Connecting-IP": "198.51.100.4", "X-Forwarded-For": "nueva"})
    afirmar_error(r, "DEMASIADOS_PEDIDOS", 429)


# ─────────────────────────────────────────────────────────────
# Limpieza del límite en memoria
# ─────────────────────────────────────────────────────────────

def test_la_limpieza_no_recorre_todo_en_cada_pedido():
    """limpiar_vencidos recorre todas las claves. Los endpoints llaman a
    limpiar_cada_tanto, que barre como mucho una vez por minuto."""
    assert ratelimit.permitido("1.2.3.4", "ab12cd34", ahora=0.0)
    vence = ratelimit.VENTANA_SEGUNDOS + 1

    assert ratelimit.limpiar_cada_tanto(ahora=vence) == 1, "la primera vez barre"
    assert ratelimit.permitido("5.6.7.8", "ab12cd34", ahora=vence)
    despues = vence + ratelimit.VENTANA_SEGUNDOS + 1
    assert ratelimit.limpiar_cada_tanto(ahora=despues - ratelimit.VENTANA_SEGUNDOS) == 0
    assert ratelimit.limpiar_cada_tanto(ahora=despues) == 1, "pasado el minuto, vuelve a barrer"
    assert ratelimit._pedidos == {}


# ─────────────────────────────────────────────────────────────
# La URL de la foto, exacta
# ─────────────────────────────────────────────────────────────

PID = "eventos/ab12cd34/k3j2h1"


@pytest.mark.parametrize(
    "url",
    [
        f"https://res.cloudinary.com/demo/image/upload/v1712345678/{PID}.jpg",
        f"https://res.cloudinary.com/demo/image/upload/{PID}.jpg",
        f"https://res.cloudinary.com/demo/image/upload/v1/{PID}.HEIC",
    ],
)
def test_la_url_que_devuelve_cloudinary_pasa(url):
    verificar_url(url, PID)


@pytest.mark.parametrize(
    "url",
    [
        # Tapa la foto con una imagen de afuera.
        "https://res.cloudinary.com/demo/image/upload/l_fetch:aHR0cHM6Ly9ldmlsLmV4YW1wbGUvYS5qcGc=,"
        f"w_1.0,fl_relative/{PID}.jpg",
        # Muestra la imagen por defecto, que es de otro evento.
        f"https://res.cloudinary.com/demo/image/upload/d_eventos:otroevt:ajena.jpg/{PID}.jpg",
        # Cualquier transformación.
        f"https://res.cloudinary.com/demo/image/upload/e_blur:2000/{PID}.jpg",
        # El navegador resuelve los .. y carga una imagen de otra cuenta.
        f"https://res.cloudinary.com/demo/image/upload/v1/{PID}/../../../../otra/image/upload/a.jpg",
        f"https://res.cloudinary.com/demo/image/upload/v1/{PID}.jpg?x=1",
        f"https://res.cloudinary.com/demo/image/upload/v1/{PID}.jpg#x",
        f"https://res.cloudinary.com/demo/image/upload/v1/{PID}.gif",
        f"https://res.cloudinary.com/demo/image/upload/v1/{PID}x.jpg",
    ],
)
def test_una_url_con_agregados_es_rechazada(url):
    with pytest.raises(ErrorApp) as e:
        verificar_url(url, PID)
    assert e.value.codigo == "ARCHIVO_INVALIDO"


def test_con_la_cuenta_configurada_otra_cuenta_no_pasa(monkeypatch):
    from app import cloudinary_service

    monkeypatch.setattr(cloudinary_service.config, "CLOUDINARY_CLOUD_NAME", "micloud")
    verificar_url(f"https://res.cloudinary.com/micloud/image/upload/v1/{PID}.jpg", PID)
    with pytest.raises(ErrorApp):
        verificar_url(f"https://res.cloudinary.com/otra/image/upload/v1/{PID}.jpg", PID)


@pytest.mark.parametrize("sufijo", ["a.b", "..", "con espacio", "x" * 101, "ñandú"])
def test_el_sufijo_del_public_id_es_el_de_cloudinary(sufijo):
    with pytest.raises(ErrorApp) as e:
        verificar_public_id(f"eventos/ab12cd34/{sufijo}", "ab12cd34")
    assert e.value.codigo == "PUBLIC_ID_AJENO"


# ─────────────────────────────────────────────────────────────
# Login
# ─────────────────────────────────────────────────────────────

def entrar(cliente, email: str, password: str, cabeceras: dict[str, str] | None = None):
    return cliente.post("/api/admin/login", json={"email": email, "password": password},
                        headers=cabeceras or {})


def test_los_topes_del_login():
    assert rutas_admin.MAXIMO_LOGINS_POR_IP == 10
    assert rutas_admin.MAXIMO_LOGINS_POR_EMAIL == 20


@sin_base
def test_el_login_tiene_tope_por_ip(cliente_con_base):
    """Cada intento cuesta un bcrypt: sin tope, se prueban contraseñas sin
    freno y se satura la única instancia en plena fiesta."""
    ip = detras_del_proxy("203.0.113.20", "inventada")
    for i in range(rutas_admin.MAXIMO_LOGINS_POR_IP):
        afirmar_error(entrar(cliente_con_base, f"prueba{i}@x.test", "mala", ip), "NO_AUTORIZADO", 401)
    # Ni con la contraseña correcta, ni inventando otra IP adelante.
    r = entrar(cliente_con_base, EMAIL_ADMIN, PASSWORD_ADMIN,
               detras_del_proxy("203.0.113.20", "otra-inventada"))
    afirmar_error(r, "DEMASIADOS_PEDIDOS", 429)

    otra_ip = detras_del_proxy("198.51.100.20", "inventada")
    assert entrar(cliente_con_base, EMAIL_ADMIN, PASSWORD_ADMIN, otra_ip).status_code == 200


@sin_base
def test_el_login_tiene_tope_por_email(cliente_con_base):
    """Desde muchas IPs contra la misma cuenta: a los 20 intentos se corta."""
    for i in range(rutas_admin.MAXIMO_LOGINS_POR_EMAIL):
        r = entrar(cliente_con_base, EMAIL_ADMIN, "mala", {"X-Forwarded-For": f"203.0.113.{i}"})
        afirmar_error(r, "NO_AUTORIZADO", 401)
    r = entrar(cliente_con_base, EMAIL_ADMIN.upper(), PASSWORD_ADMIN, {"X-Forwarded-For": "198.51.100.1"})
    afirmar_error(r, "DEMASIADOS_PEDIDOS", 429)
    assert entrar(cliente_con_base, "otra@x.test", "mala",
                  {"X-Forwarded-For": "198.51.100.1"}).status_code == 401, "otra cuenta sigue"


# ─────────────────────────────────────────────────────────────
# Firma y registro de cuentas: la XFF inventada no evade nada
# ─────────────────────────────────────────────────────────────

@sin_base
def test_inventar_x_forwarded_for_no_evade_el_tope_de_firma(cliente_con_base, eventos):
    ruta = f"/api/e/{CODIGO_ACTIVO}/firma"
    for i in range(rutas_publico.MAXIMO_FIRMAS_POR_DISPOSITIVO):
        r = cliente_con_base.post(ruta, json={"dispositivo_hash": DISPOSITIVO},
                                  headers=detras_del_proxy("203.0.113.30", f"10.1.{i}.1"))
        assert r.status_code == 200, r.text
    r = cliente_con_base.post(ruta, json={"dispositivo_hash": DISPOSITIVO},
                              headers=detras_del_proxy("203.0.113.30", "una-mas"))
    afirmar_error(r, "DEMASIADOS_PEDIDOS", 429)


@sin_base
def test_inventar_x_forwarded_for_no_evade_el_tope_de_registro(cliente_con_base):
    cuerpo = {"nombre": "Serie", "password": "una-clave-larga"}
    for i in range(rutas_cuentas.MAXIMO_REGISTROS):
        r = cliente_con_base.post("/api/cuentas/registro", json={**cuerpo, "email": f"s{i}@x.test"},
                                  headers=detras_del_proxy("203.0.113.40", f"10.2.{i}.1"))
        assert r.status_code == 201, r.text
    r = cliente_con_base.post("/api/cuentas/registro", json={**cuerpo, "email": "otra@x.test"},
                              headers=detras_del_proxy("203.0.113.40", "una-mas"))
    afirmar_error(r, "DEMASIADOS_PEDIDOS", 429)


# ─────────────────────────────────────────────────────────────
# Registro de fotos
# ─────────────────────────────────────────────────────────────

def cuerpo_foto(sufijo: str, dispositivo: str = DISPOSITIVO, **cambios) -> dict:
    pid = f"eventos/{CODIGO_ACTIVO}/{sufijo}"
    return {"public_id": pid, "url": url_de(pid), "ancho": 800, "alto": 600, "bytes": 1000,
            "dispositivo_hash": dispositivo, **cambios}


def registrar(cliente, cuerpo: dict, ip: str = "203.0.113.60", inventada: str = "x"):
    return cliente.post(f"/api/e/{CODIGO_ACTIVO}/fotos", json=cuerpo,
                        headers=detras_del_proxy(ip, inventada))


def cantidad_de_fotos(db) -> int:
    db.expire_all()
    return db.scalar(select(func.count()).select_from(Foto))


def test_los_topes_de_registro_de_fotos():
    """Los mismos números que la firma: un invitado real nunca llega."""
    assert rutas_publico.MAXIMO_REGISTROS_POR_DISPOSITIVO == 30
    assert rutas_publico.MAXIMO_REGISTROS_POR_CONEXION == 600


@sin_base
def test_rotar_el_dispositivo_no_evade_el_tope_por_conexion(cliente_con_base, eventos, db,
                                                            monkeypatch):
    """Antes, 700 registros desde una conexión rotando dispositivo_hash daban
    700 pendientes. El tope real es 600; acá se baja para no insertar 600 filas."""
    monkeypatch.setattr(rutas_publico, "MAXIMO_REGISTROS_POR_CONEXION", 5)
    for i in range(5):
        r = registrar(cliente_con_base, cuerpo_foto(f"rota{i}", f"celular-{i:03d}".ljust(32, "0")),
                      inventada=f"10.3.{i}.1")
        assert r.status_code == 201, r.text
    antes = cantidad_de_fotos(db)
    r = registrar(cliente_con_base, cuerpo_foto("rota99", "celular-999".ljust(32, "0")),
                  inventada="otra")
    afirmar_error(r, "DEMASIADOS_PEDIDOS", 429)
    assert cantidad_de_fotos(db) == antes

    r = registrar(cliente_con_base, cuerpo_foto("otraip", "celular-998".ljust(32, "0")),
                  ip="198.51.100.60")
    assert r.status_code == 201, "el tope es por conexión: otro salón no queda bloqueado"


@sin_base
def test_el_registro_de_fotos_tiene_tope_por_celular(cliente_con_base, eventos, monkeypatch):
    monkeypatch.setattr(rutas_publico, "MAXIMO_REGISTROS_POR_DISPOSITIVO", 3)
    for i in range(3):
        assert registrar(cliente_con_base, cuerpo_foto(f"cel{i}")).status_code == 201
    afirmar_error(registrar(cliente_con_base, cuerpo_foto("cel9")), "DEMASIADOS_PEDIDOS", 429)
    otro = cuerpo_foto("cel10", "otro-celular".ljust(32, "0"))
    assert registrar(cliente_con_base, otro).status_code == 201, "el resto del salón sigue"


@sin_base
@pytest.mark.parametrize(
    "cambios",
    [
        {"url": f"https://res.cloudinary.com/demo/image/upload/{'x' * 500}/"
                f"eventos/{CODIGO_ACTIVO}/larga.jpg"},
        {"public_id": f"eventos/{CODIGO_ACTIVO}/{'a' * 3000}",
         "url": url_de(f"eventos/{CODIGO_ACTIVO}/{'a' * 3000}")},
    ],
)
def test_url_o_public_id_demasiado_largos(cliente_con_base, eventos, db, cambios):
    """Una url de un mega entraba entera a la base; un public_id de 3000
    caracteres rompía el índice único con un 500 fuera del contrato."""
    antes = cantidad_de_fotos(db)
    afirmar_error(registrar(cliente_con_base, cuerpo_foto("larga", **cambios)), "DATOS_INVALIDOS", 422)
    assert cantidad_de_fotos(db) == antes


@sin_base
@pytest.mark.parametrize(
    "url",
    [
        "https://res.cloudinary.com/demo/image/upload/l_fetch:aHR0cHM6Ly9ldmlsLmV4YW1wbGUvYS5qcGc=/"
        f"eventos/{CODIGO_ACTIVO}/trucha.jpg",
        f"https://res.cloudinary.com/demo/image/upload/d_eventos:otro:x.jpg/eventos/{CODIGO_ACTIVO}/trucha.jpg",
        f"https://res.cloudinary.com/demo/image/upload/v1/eventos/{CODIGO_ACTIVO}/trucha/../../x/a.jpg",
    ],
)
def test_no_se_registra_una_url_con_agregados(cliente_con_base, eventos, db, url):
    antes = cantidad_de_fotos(db)
    afirmar_error(registrar(cliente_con_base, cuerpo_foto("trucha", url=url)), "ARCHIVO_INVALIDO", 400)
    assert cantidad_de_fotos(db) == antes
