"""Fase 2: base, modelos y autenticación de verdad.

Criterio de aceptación del brief: se hace login con un administrador del seed,
se crea un evento y las dos claves son distintas entre sí y no derivan del id.

Necesitan Postgres. Definí DATABASE_URL_TEST o se saltean solas.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models import Evento
from tests.conftest import EMAIL_ADMIN, PASSWORD_ADMIN, sin_base

pytestmark = sin_base


def afirmar_error(respuesta, codigo_esperado: str, http_esperado: int) -> None:
    assert respuesta.status_code == http_esperado, respuesta.text
    cuerpo = respuesta.json()
    assert set(cuerpo.keys()) == {"error"}
    assert set(cuerpo["error"].keys()) == {"codigo", "mensaje"}
    assert cuerpo["error"]["codigo"] == codigo_esperado


# ─────────────────────────────────────────────────────────────
# Sesión
# ─────────────────────────────────────────────────────────────

def test_login_con_administrador_del_seed(cliente_con_base):
    r = cliente_con_base.post(
        "/api/admin/login", json={"email": EMAIL_ADMIN, "password": PASSWORD_ADMIN}
    )
    assert r.status_code == 200, r.text
    assert set(r.json().keys()) == {"token", "expira_en"}
    assert r.json()["token"].count(".") == 2, "tiene que ser un JWT"


def test_login_no_distingue_mail_inexistente_de_clave_incorrecta(cliente_con_base):
    """Si los mensajes fueran distintos se podría averiguar qué mails existen."""
    mal_clave = cliente_con_base.post(
        "/api/admin/login", json={"email": EMAIL_ADMIN, "password": "incorrecta"}
    )
    no_existe = cliente_con_base.post(
        "/api/admin/login", json={"email": "nadie@ejemplo.test", "password": PASSWORD_ADMIN}
    )
    afirmar_error(mal_clave, "NO_AUTORIZADO", 401)
    afirmar_error(no_existe, "NO_AUTORIZADO", 401)
    assert mal_clave.json() == no_existe.json()


def test_login_ignora_mayusculas_y_espacios_en_el_mail(cliente_con_base):
    r = cliente_con_base.post(
        "/api/admin/login",
        json={"email": f"  {EMAIL_ADMIN.upper()}  ", "password": PASSWORD_ADMIN},
    )
    assert r.status_code == 200, r.text


def test_token_invalido_no_abre_el_panel(cliente_con_base):
    r = cliente_con_base.get(
        "/api/admin/eventos", headers={"Authorization": "Bearer no-es-un-jwt"}
    )
    afirmar_error(r, "NO_AUTORIZADO", 401)


def test_token_firmado_con_otro_secreto_no_sirve(cliente_con_base):
    import jwt

    ajeno = jwt.encode({"sub": "1"}, "otro-secreto-cualquiera-de-mas-de-32-caracteres", algorithm="HS256")
    r = cliente_con_base.get("/api/admin/eventos", headers={"Authorization": f"Bearer {ajeno}"})
    afirmar_error(r, "NO_AUTORIZADO", 401)


# ─────────────────────────────────────────────────────────────
# Alta de evento y sus dos claves
# ─────────────────────────────────────────────────────────────

def test_crear_evento(autorizado):
    r = autorizado.post(
        "/api/admin/eventos",
        json={"nombre": "Casamiento de prueba", "fecha_evento": "2026-12-01"},
    )
    assert r.status_code == 201, r.text
    e = r.json()
    assert e["estado"] == "borrador", "un evento nace sin publicar"
    assert e["pendientes"] == e["aprobadas"] == e["rechazadas"] == 0


def test_las_dos_claves_son_distintas_y_del_largo_correcto(autorizado):
    e = autorizado.post(
        "/api/admin/eventos", json={"nombre": "Fiesta", "fecha_evento": "2026-12-01"}
    ).json()
    assert e["codigo_publico"] != e["token_pantalla"]
    assert len(e["codigo_publico"]) == 8, "8 caracteres: es el que va en el QR"
    assert len(e["token_pantalla"]) == 32, "32 caracteres: el de la notebook"


def test_las_claves_no_derivan_del_id(autorizado):
    """Si fueran adivinables, el aislamiento entre eventos no existiría.

    No se busca el id como subcadena: una clave aleatoria de 32 caracteres
    contiene un dígito cualquiera casi siempre, así que esa prueba fallaría sola
    de a ratos sin que nada esté mal. Se verifican tres propiedades que una
    clave derivada del id no puede cumplir.
    """
    creados = [
        autorizado.post(
            "/api/admin/eventos", json={"nombre": "Mismo nombre", "fecha_evento": "2026-12-01"}
        ).json()
        for _ in range(8)
    ]
    ids = [e["id"] for e in creados]
    codigos = [e["codigo_publico"] for e in creados]
    tokens = [e["token_pantalla"] for e in creados]

    assert ids == sorted(ids), "los ids sí son secuenciales; ese es justamente el punto"

    # 1. Entrada idéntica, claves distintas: no son función de lo que se manda.
    assert len(set(codigos)) == len(codigos)
    assert len(set(tokens)) == len(tokens)

    # 2. Ids consecutivos y claves sin ordenar: no hay monotonía con el id.
    #    Con ocho muestras, que salgan ordenadas por azar es 1 en 40320.
    assert codigos != sorted(codigos)
    assert tokens != sorted(tokens)

    # 3. Varían en toda su extensión, no sólo en un sufijo pegado a un prefijo fijo.
    assert len({c[0] for c in codigos}) > 1, "el primer carácter no es siempre el mismo"
    assert len({t[:4] for t in tokens}) == len(tokens), "no hay prefijo común"


def test_el_evento_creado_queda_en_la_base(autorizado, db):
    e = autorizado.post(
        "/api/admin/eventos", json={"nombre": "  Con espacios  ", "fecha_evento": "2026-12-01"}
    ).json()
    fila = db.scalar(select(Evento).where(Evento.codigo_publico == e["codigo_publico"]))
    assert fila is not None
    assert fila.nombre == "Con espacios", "el nombre se guarda sin espacios de sobra"
    assert fila.estado == "borrador"
    assert fila.max_fotos_por_dispositivo == 10, "el default del esquema"
    assert fila.segundos_por_foto == 7
    assert fila.creado_en.tzinfo is not None, "timestamptz, nunca timestamp pelado"


def test_nombre_vacio_es_rechazado(autorizado):
    r = autorizado.post("/api/admin/eventos", json={"nombre": "", "fecha_evento": "2026-12-01"})
    afirmar_error(r, "DATOS_INVALIDOS", 422)


# ─────────────────────────────────────────────────────────────
# Listado
# ─────────────────────────────────────────────────────────────

def test_listado_vacio(autorizado):
    r = autorizado.get("/api/admin/eventos")
    assert r.status_code == 200
    assert r.json() == []


def test_listado_trae_los_totales_por_estado(autorizado, db):
    e = autorizado.post(
        "/api/admin/eventos", json={"nombre": "Con fotos", "fecha_evento": "2026-12-01"}
    ).json()
    from app.models import Foto

    evento = db.scalar(select(Evento).where(Evento.id == e["id"]))
    for i, estado in enumerate(["aprobada"] * 3 + ["pendiente"] * 2 + ["rechazada"]):
        db.add(
            Foto(
                evento_id=evento.id,
                public_id=f"eventos/{evento.codigo_publico}/f{i}",
                url="https://res.cloudinary.com/demo/image/upload/sample.jpg",
                estado=estado,
            )
        )
    db.commit()

    fila = next(x for x in autorizado.get("/api/admin/eventos").json() if x["id"] == e["id"])
    assert (fila["aprobadas"], fila["pendientes"], fila["rechazadas"]) == (3, 2, 1)


def test_un_organizador_no_ve_los_eventos_de_otro(autorizado_organizador, autorizado):
    """El aislamiento no es sólo entre eventos: también entre cuentas. Ana es
    admin y ve todo; Bruno es organizador y ve sólo lo suyo."""
    autorizado_organizador.post(
        "/api/admin/eventos", json={"nombre": "Mío", "fecha_evento": "2026-12-01"}
    )
    autorizado.post("/api/admin/eventos", json={"nombre": "Ajeno", "fecha_evento": "2026-12-02"})

    nombres = [e["nombre"] for e in autorizado_organizador.get("/api/admin/eventos").json()]
    assert nombres == ["Mío"]


# ─────────────────────────────────────────────────────────────
# Ids fuera de rango
# ─────────────────────────────────────────────────────────────

ENORME = 10**20  # no entra en bigint


@pytest.mark.parametrize(
    "metodo,ruta,cuerpo",
    [
        ("get", f"/api/admin/eventos/{ENORME}/resumen", None),
        ("get", f"/api/admin/eventos?organizador={ENORME}", None),
        ("patch", f"/api/admin/fotos/{ENORME}", {"estado": "aprobada"}),
        ("patch", f"/api/admin/cuentas/{ENORME}", {"estado": "activa"}),
        (
            "post",
            "/api/admin/eventos",
            {"nombre": "x", "fecha_evento": "2026-12-01", "organizador_id": ENORME},
        ),
    ],
)
def test_un_id_que_no_entra_en_bigint_es_datos_invalidos(autorizado, metodo, ruta, cuerpo):
    """Python no le pone tope a un int y Postgres sí: sin el manejador de
    DataError, psycopg levanta una excepción y sale un 500."""
    extra = {"json": cuerpo} if cuerpo is not None else {}
    r = getattr(autorizado, metodo)(ruta, **extra)
    afirmar_error(r, "DATOS_INVALIDOS", 422)
