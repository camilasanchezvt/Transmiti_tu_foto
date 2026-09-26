"""La superficie de la API, sin tocar la base.

Verifica que /docs liste exactamente los endpoints del contrato, que todos
documenten sus errores, y que las respuestas que no dependen de la base
respeten el formato de la sección 5.

El comportamiento de cada endpoint se prueba en test_fase2.py y test_fase3.py,
que sí necesitan Postgres.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.database import get_db
from app.main import app


class SesionCaida:
    """Una base que no contesta, sin esperar a que se rinda TCP.

    Estas pruebas no deben tocar Postgres. Sin este reemplazo, /api/salud se
    conecta al DATABASE_URL de verdad y, si ahí no hay nada escuchando, el
    pedido queda colgado más de un minuto.
    """

    def execute(self, *_args, **_kwargs):
        raise OperationalError("sin base en estas pruebas", None, Exception())

    def close(self) -> None:
        pass


@pytest.fixture(scope="module")
def cliente() -> TestClient:
    def get_db_caida():
        yield SesionCaida()

    app.dependency_overrides[get_db] = get_db_caida
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def afirmar_error(respuesta, codigo_esperado: str, http_esperado: int) -> None:
    assert respuesta.status_code == http_esperado, respuesta.text
    cuerpo = respuesta.json()
    assert set(cuerpo.keys()) == {"error"}
    assert set(cuerpo["error"].keys()) == {"codigo", "mensaje"}
    assert cuerpo["error"]["codigo"] == codigo_esperado
    assert isinstance(cuerpo["error"]["mensaje"], str) and cuerpo["error"]["mensaje"]


# ─────────────────────────────────────────────────────────────
# Los catorce endpoints
# ─────────────────────────────────────────────────────────────

DEL_CONTRATO = [
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

# Endpoints agregados FUERA del contrato de la sección 5, propuestos y aprobados
# antes de escribirlos como pide la regla 9.
#
# Existen porque el link de la pantalla mide 68 caracteres y hay que poder
# cargarlo con el control remoto de una tele: el panel genera seis dígitos y la
# tele los canjea por el token.
#
# Esta lista es la que hace que el agregado sea deliberado y no un descuido: si
# aparece un endpoint que no está acá ni en el contrato, la prueba de abajo falla.
AGREGADOS = [
    ("POST", "/api/admin/eventos/{id_evento}/vincular"),
    ("POST", "/api/pantalla/canjear"),
    # El video del evento: Cloudinary lo arma en segundo plano con las aprobadas
    # (create_slideshow) y el panel consulta hasta que está listo.
    ("GET", "/api/admin/eventos/{id_evento}/video"),
    ("POST", "/api/admin/eventos/{id_evento}/video"),
    # Cuentas y roles (25-sep-2026). Hay admins, que ven todo, y organizadores,
    # que ven sólo sus eventos. Las cuentas se piden solas desde el registro
    # público y nacen pendientes hasta que un admin las habilita: así ningún
    # admin crea cuentas con contraseña ni conoce contraseñas ajenas.
    ("POST", "/api/cuentas/registro"),
    # Quién tiene la sesión abierta: el panel lo necesita para saber si
    # mostrar la pestaña de cuentas, que es sólo para admins.
    ("GET", "/api/admin/yo"),
    # Listar las cuentas con su historial y habilitarlas, darlas de baja,
    # reactivarlas o cambiarles el rol. Dar de baja reemplaza a borrar.
    ("GET", "/api/admin/cuentas"),
    ("PATCH", "/api/admin/cuentas/{id_cuenta}"),
    # Eliminar una cuenta para siempre (26-sep-2026): la única excepción a
    # "nada se borra", sólo para superadmins. Sus eventos pasan a quien la
    # elimina, y el email de la cuenta se confirma en el cuerpo, no en la URL.
    ("DELETE", "/api/admin/cuentas/{id_cuenta}"),
    # Olvidé mi contraseña (26-sep-2026): sin sesión. `recuperar` manda un link
    # por email (Brevo) y responde siempre lo mismo, exista o no la cuenta;
    # `restablecer` canjea el token del link por una contraseña nueva y cierra
    # todas las sesiones de la cuenta.
    ("POST", "/api/cuentas/recuperar"),
    ("POST", "/api/cuentas/restablecer"),
    # Mi cuenta (26-sep-2026): cada cuenta cambia su nombre, su tema del panel
    # y los predeterminados de sus eventos nuevos; su contraseña (con la
    # actual; devuelve una sesión nueva), y su avatar, que el navegador sube
    # directo a Cloudinary con una firma, como las fotos de los invitados.
    ("PATCH", "/api/admin/yo"),
    ("POST", "/api/admin/yo/contrasena"),
    ("POST", "/api/admin/yo/avatar/firma"),
    ("PUT", "/api/admin/yo/avatar"),
    ("POST", "/api/admin/yo/avatar/quitar"),
]


def rutas_publicadas(cliente) -> set[tuple[str, str]]:
    esquema = cliente.get("/openapi.json").json()
    return {
        (metodo.upper(), ruta)
        for ruta, operaciones in esquema["paths"].items()
        for metodo in operaciones
        if ruta.startswith("/api")
    }


def test_los_catorce_endpoints_del_contrato(cliente):
    """14 del contrato + /api/salud, que el brief marca aparte ("— sin auth —").

    Se mira el esquema OpenAPI, que es exactamente lo que lista /docs.
    """
    rutas = rutas_publicadas(cliente)
    del_contrato = sorted(
        x for x in rutas if x[1] != "/api/salud" and x not in AGREGADOS
    )
    assert len(del_contrato) == 14, del_contrato
    assert del_contrato == DEL_CONTRATO
    assert ("GET", "/api/salud") in rutas


def test_no_hay_endpoints_inventados(cliente):
    """Regla 9: no inventar endpoints fuera del contrato.

    Los de AGREGADOS están permitidos porque se propusieron y se aprobaron. Todo
    lo demás que aparezca acá es un endpoint inventado.
    """
    de_mas = (
        rutas_publicadas(cliente)
        - set(DEL_CONTRATO)
        - set(AGREGADOS)
        - {("GET", "/api/salud")}
    )
    assert de_mas == set(), f"endpoints fuera del contrato: {sorted(de_mas)}"


def test_los_agregados_estan_publicados(cliente):
    """Si alguno desaparece, se perdió algo que se agregó a propósito: la
    vinculación por código corto, el video, las cuentas, eliminarlas, recuperar
    la contraseña o Mi cuenta."""
    rutas = rutas_publicadas(cliente)
    faltan = [x for x in AGREGADOS if x not in rutas]
    assert faltan == [], faltan


def test_los_errores_estan_documentados_en_docs(cliente):
    """El criterio de la Fase 1 pide la forma del contrato «incluidos los errores»."""
    esquema = cliente.get("/openapi.json").json()
    sin_errores = [
        f"{m.upper()} {ruta}"
        for ruta, operaciones in esquema["paths"].items()
        if ruta.startswith("/api") and ruta != "/api/salud"
        for m, op in operaciones.items()
        if not [c for c in op.get("responses", {}) if c.startswith(("4", "5"))]
    ]
    assert sin_errores == [], sin_errores


def test_el_esquema_de_error_es_uno_solo(cliente):
    esquema = cliente.get("/openapi.json").json()
    assert "RespuestaError" in esquema["components"]["schemas"]
    detalle = esquema["components"]["schemas"]["DetalleError"]["properties"]
    assert set(detalle.keys()) == {"codigo", "mensaje"}


def test_docs_no_promete_el_422_crudo_de_fastapi(cliente):
    """La API responde {"error": {...}} también en un 422 (manejar_validacion).
    /docs no puede documentar el {"detail": [...]} que FastAPI pone solo."""
    esquema = cliente.get("/openapi.json").json()
    assert "HTTPValidationError" not in esquema["components"]["schemas"]
    crudos = [
        f"{m.upper()} {ruta}"
        for ruta, operaciones in esquema["paths"].items()
        for m, op in operaciones.items()
        if "422" in op.get("responses", {})
        and op["responses"]["422"]["content"]["application/json"]["schema"]["$ref"]
        != "#/components/schemas/RespuestaError"
    ]
    assert crudos == [], crudos


def test_un_422_real_tiene_la_forma_del_contrato(cliente):
    afirmar_error(cliente.post("/api/pantalla/canjear", json={}), "DATOS_INVALIDOS", 422)


def test_la_descripcion_de_docs_no_es_la_de_la_fase_1(cliente):
    descripcion = cliente.get("/openapi.json").json()["info"]["description"]
    assert "Fase 1" not in descripcion
    assert "datos fijos" not in descripcion


# ─────────────────────────────────────────────────────────────
# Autorización y errores que no dependen de la base
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
    ("post", "/api/admin/eventos/1/vincular"),
    ("get", "/api/admin/eventos/1/video"),
    ("post", "/api/admin/eventos/1/video"),
    ("get", "/api/admin/yo"),
    ("get", "/api/admin/cuentas"),
    ("patch", "/api/admin/cuentas/1"),
    ("delete", "/api/admin/cuentas/1"),
    ("patch", "/api/admin/yo"),
    ("post", "/api/admin/yo/contrasena"),
    ("post", "/api/admin/yo/avatar/firma"),
    ("put", "/api/admin/yo/avatar"),
    ("post", "/api/admin/yo/avatar/quitar"),
]


@pytest.mark.parametrize("metodo,ruta", RUTAS_PROTEGIDAS)
def test_sin_bearer_es_no_autorizado(cliente, metodo, ruta):
    """Se rechaza antes de consultar la base, así que no hace falta Postgres."""
    afirmar_error(getattr(cliente, metodo)(ruta), "NO_AUTORIZADO", 401)


def test_ruta_inexistente_respeta_el_contrato(cliente):
    r = cliente.get("/api/no-existe")
    assert r.status_code == 404
    assert set(r.json().keys()) == {"error"}


def test_metodo_no_permitido_respeta_el_contrato(cliente):
    r = cliente.delete("/api/salud")
    assert r.status_code == 405
    assert set(r.json().keys()) == {"error"}


# ─────────────────────────────────────────────────────────────
# Salud
# ─────────────────────────────────────────────────────────────

def test_salud_sin_auth(cliente):
    r = cliente.get("/api/salud")
    assert r.status_code == 200
    assert set(r.json().keys()) == {"estado", "base"}


def test_salud_responde_200_aunque_la_base_este_caida(cliente):
    """El fixture usa una base que no contesta, así que esto prueba el caso real.

    Si devolviera un error, Render reiniciaría el servicio en loop por un
    problema que no es del servicio: cuando Supabase gratuito se pausa, lo que
    hay que despertar es Supabase, no la API.
    """
    r = cliente.get("/api/salud")
    assert r.status_code == 200
    assert r.json()["estado"] == "ok"
    assert r.json()["base"] == "caida"
