"""Fase 3: fotos y pantalla contra la base de verdad.

Criterio de aceptación del brief: un `public_id` de otra carpeta devuelve
PUBLIC_ID_AJENO, y `?desde=N` devuelve sólo aprobadas con id mayor a N.

Necesitan Postgres. Definí DATABASE_URL_TEST o se saltean solas.
"""

from __future__ import annotations

import hashlib

import pytest
from sqlalchemy import select

from app import ratelimit
from app.cloudinary_service import firmar
from app.models import Foto
from app.routers import publico as rutas_publico
from tests.conftest import (
    CODIGO_ACTIVO,
    CODIGO_BORRADOR,
    CODIGO_CERRADO,
    TOKEN_ACTIVO,
    TOKEN_BORRADOR,
    TOKEN_CERRADO,
    sin_base,
    url_de,
)

pytestmark = sin_base

DISPOSITIVO = "9f2c1a7b4e8d0c35a6b8d0e2f4061835"


def afirmar_error(respuesta, codigo_esperado: str, http_esperado: int) -> None:
    assert respuesta.status_code == http_esperado, respuesta.text
    cuerpo = respuesta.json()
    assert set(cuerpo.keys()) == {"error"}
    assert set(cuerpo["error"].keys()) == {"codigo", "mensaje"}
    assert cuerpo["error"]["codigo"] == codigo_esperado


def cuerpo_foto(codigo: str = CODIGO_ACTIVO, sufijo: str = "nueva01", **cambios) -> dict:
    pid = f"eventos/{codigo}/{sufijo}"
    base = {
        "public_id": pid,
        "url": url_de(pid),
        "ancho": 1600,
        "alto": 1200,
        "bytes": 348211,
        "dispositivo_hash": DISPOSITIVO,
        "nombre_invitado": "Sofi",
    }
    base.update(cambios)
    return base


# ─────────────────────────────────────────────────────────────
# Evento público
# ─────────────────────────────────────────────────────────────

def test_evento_publico(cliente_con_base, eventos):
    r = cliente_con_base.get(f"/api/e/{CODIGO_ACTIVO}")
    assert r.status_code == 200
    assert set(r.json().keys()) == {
        "nombre", "fecha_evento", "estado", "max_fotos_por_dispositivo"
    }
    assert "id" not in r.json(), "regla 1: el id interno no sale en respuestas públicas"
    assert "token_pantalla" not in r.json(), "el código de subir no revela el de leer"


def test_evento_cerrado_sigue_respondiendo(cliente_con_base, eventos):
    """Para que la app pueda mostrar la pantalla de cierre."""
    r = cliente_con_base.get(f"/api/e/{CODIGO_CERRADO}")
    assert r.status_code == 200
    assert r.json()["estado"] == "cerrado"


def test_evento_borrador_no_existe_hacia_afuera(cliente_con_base, eventos):
    r = cliente_con_base.get(f"/api/e/{CODIGO_BORRADOR}")
    afirmar_error(r, "EVENTO_NO_ENCONTRADO", 404)


def test_evento_inexistente(cliente_con_base, eventos):
    afirmar_error(cliente_con_base.get("/api/e/noexiste"), "EVENTO_NO_ENCONTRADO", 404)


# ─────────────────────────────────────────────────────────────
# Firma
# ─────────────────────────────────────────────────────────────

def test_firma(cliente_con_base, eventos):
    r = cliente_con_base.post(
        f"/api/e/{CODIGO_ACTIVO}/firma", json={"dispositivo_hash": DISPOSITIVO}
    )
    assert r.status_code == 200, r.text
    assert set(r.json().keys()) == {
        "cloud_name", "api_key", "timestamp", "signature", "folder"
    }
    assert r.json()["folder"] == f"eventos/{CODIGO_ACTIVO}"


def test_la_firma_es_la_que_espera_cloudinary(monkeypatch):
    """El algoritmo: parámetros ordenados, unidos por &, api_secret al final, SHA-1."""
    from app import cloudinary_service

    monkeypatch.setattr(cloudinary_service.config, "CLOUDINARY_API_SECRET", "secreto-de-prueba")
    monkeypatch.setattr(cloudinary_service.config, "CLOUDINARY_CLOUD_NAME", "minube")
    monkeypatch.setattr(cloudinary_service.config, "CLOUDINARY_API_KEY", "123")

    resultado = firmar("ab12cd34", momento=1756200000)
    esperado = hashlib.sha1(
        b"folder=eventos/ab12cd34&timestamp=1756200000secreto-de-prueba"
    ).hexdigest()
    assert resultado["signature"] == esperado
    assert resultado["cloud_name"] == "minube"


def test_la_firma_nunca_devuelve_el_secreto(cliente_con_base, eventos):
    """Regla 2: el CLOUDINARY_API_SECRET vive sólo en el backend."""
    from app import cloudinary_service

    r = cliente_con_base.post(
        f"/api/e/{CODIGO_ACTIVO}/firma", json={"dispositivo_hash": DISPOSITIVO}
    )
    assert "api_secret" not in r.text
    assert "CLOUDINARY_API_SECRET" not in r.text
    secreto = cloudinary_service.config.CLOUDINARY_API_SECRET
    if secreto:
        assert secreto not in r.text


def test_firma_de_evento_cerrado(cliente_con_base, eventos):
    r = cliente_con_base.post(
        f"/api/e/{CODIGO_CERRADO}/firma", json={"dispositivo_hash": DISPOSITIVO}
    )
    afirmar_error(r, "EVENTO_CERRADO", 409)


def firmar_desde(cliente, dispositivo: str, ip: str = "203.0.113.50", codigo: str = CODIGO_ACTIVO):
    """Todos los pedidos salen de la misma IP, como el wifi de un salón."""
    return cliente.post(f"/api/e/{codigo}/firma", json={"dispositivo_hash": dispositivo},
                        headers={"X-Forwarded-For": ip})


def celular(n: int) -> str:
    return f"celular-{n:05d}".ljust(32, "0")


def test_los_topes_de_firma():
    """30 por celular y 600 por conexión, cada 10 minutos. Si alguien los
    cambia, que sea a propósito: la sección 5 los documenta."""
    assert rutas_publico.MAXIMO_FIRMAS_POR_DISPOSITIVO == 30
    assert rutas_publico.MAXIMO_FIRMAS_POR_CONEXION == 600
    assert ratelimit.VENTANA_SEGUNDOS == 600


def test_firma_tope_por_celular(cliente_con_base, eventos):
    """30 firmas cada 10 minutos por IP, evento y celular: la 31 del mismo celular es 429."""
    for i in range(rutas_publico.MAXIMO_FIRMAS_POR_DISPOSITIVO):
        r = firmar_desde(cliente_con_base, DISPOSITIVO)
        assert r.status_code == 200, f"el pedido {i + 1} no debería haberse frenado"
    afirmar_error(firmar_desde(cliente_con_base, DISPOSITIVO), "DEMASIADOS_PEDIDOS", 429)


def test_muchos_celulares_desde_la_misma_ip_no_se_bloquean(cliente_con_base, eventos):
    """El wifi del salón: todos salen por la misma IP. Con un celular ya frenado,
    31 celulares más desde esa IP firman igual."""
    for _ in range(rutas_publico.MAXIMO_FIRMAS_POR_DISPOSITIVO):
        firmar_desde(cliente_con_base, DISPOSITIVO)
    afirmar_error(firmar_desde(cliente_con_base, DISPOSITIVO), "DEMASIADOS_PEDIDOS", 429)

    for n in range(31):
        r = firmar_desde(cliente_con_base, celular(n))
        assert r.status_code == 200, f"el celular {n + 1} no debería haberse frenado: {r.text}"


def test_el_mismo_celular_desde_otra_ip_tiene_su_propia_cuenta(cliente_con_base, eventos):
    """La cuenta es por (IP, evento, celular): si pasa del wifi a los datos, arranca de nuevo."""
    for _ in range(rutas_publico.MAXIMO_FIRMAS_POR_DISPOSITIVO):
        firmar_desde(cliente_con_base, DISPOSITIVO)
    afirmar_error(firmar_desde(cliente_con_base, DISPOSITIVO), "DEMASIADOS_PEDIDOS", 429)
    assert firmar_desde(cliente_con_base, DISPOSITIVO, ip="198.51.100.20").status_code == 200


def test_firma_tope_por_conexion(cliente_con_base, eventos):
    """600 cada 10 minutos por IP y evento, sumando todos los celulares: frena a
    un script que inventa un dispositivo por pedido. Otra IP sigue firmando."""
    tope = rutas_publico.MAXIMO_FIRMAS_POR_CONEXION
    por_celular = rutas_publico.MAXIMO_FIRMAS_POR_DISPOSITIVO
    for i in range(tope):
        r = firmar_desde(cliente_con_base, celular(i // por_celular))
        assert r.status_code == 200, f"el pedido {i + 1} no debería haberse frenado: {r.text}"

    afirmar_error(firmar_desde(cliente_con_base, celular(99999)), "DEMASIADOS_PEDIDOS", 429)
    assert firmar_desde(cliente_con_base, celular(99999), ip="198.51.100.20").status_code == 200


def test_un_celular_frenado_no_gasta_el_tope_de_la_conexion():
    """Las dos cuentas se anotan juntas o ninguna. Un celular que insiste
    después de su tope no le come lugar al resto del salón. Con topes chicos
    para verlo entero: 2 por celular y 3 por conexión."""
    def pide(dispositivo: str) -> bool:
        return ratelimit.permitido_en_todas(
            [(("1.2.3.4", CODIGO_ACTIVO, dispositivo), 2), (("1.2.3.4", CODIGO_ACTIVO), 3)],
            ahora=0.0,
        )

    assert pide("a") and pide("a")
    assert not any(pide("a") for _ in range(50)), "el celular a ya gastó sus dos"
    assert pide("b"), "los 50 intentos frenados de a no contaron para la conexión"
    assert not pide("c"), "la conexión llegó a 3"
    assert not pide("b"), "b tiene lugar, pero la conexión no"


def test_una_conexion_llena_no_le_gasta_la_cuota_a_un_celular():
    """Topes de 2 y 2. `a` llena la conexión en el segundo 0; `b` insiste cinco
    veces en el 300 y lo frena la conexión. En el 601 se liberan las marcas de
    `a`, y `b` tiene sus dos firmas enteras: los cinco intentos frenados, que
    seguirían dentro de la ventana, no le contaron."""
    def pide(dispositivo: str, momento: float) -> bool:
        return ratelimit.permitido_en_todas(
            [(("1.2.3.4", CODIGO_ACTIVO, dispositivo), 2), (("1.2.3.4", CODIGO_ACTIVO), 2)],
            ahora=momento,
        )

    assert pide("a", 0.0) and pide("a", 0.0)
    assert not any(pide("b", 300.0) for _ in range(5))
    despues = ratelimit.VENTANA_SEGUNDOS + 1
    assert pide("b", despues) and pide("b", despues)
    assert not pide("b", despues)


def test_un_pedido_frenado_no_crea_cuentas_nuevas():
    """Un script que inventa un dispositivo por pedido contra una conexión llena
    no hace crecer el diccionario del límite."""
    conexion = (("1.2.3.4", CODIGO_ACTIVO), 1)
    assert ratelimit.permitido_en_todas([(("1.2.3.4", CODIGO_ACTIVO, "a"), 30), conexion],
                                        ahora=0.0)
    antes = len(ratelimit._pedidos)
    for n in range(100):
        assert not ratelimit.permitido_en_todas(
            [(("1.2.3.4", CODIGO_ACTIVO, f"inventado-{n}"), 30), conexion], ahora=0.0
        )
    assert len(ratelimit._pedidos) == antes


def test_el_tope_se_libera_a_los_diez_minutos():
    clave = [(("1.2.3.4", CODIGO_ACTIVO, "a"), 1)]
    assert ratelimit.permitido_en_todas(clave, ahora=0.0)
    assert not ratelimit.permitido_en_todas(clave, ahora=ratelimit.VENTANA_SEGUNDOS - 1)
    assert ratelimit.permitido_en_todas(clave, ahora=ratelimit.VENTANA_SEGUNDOS + 1)


def test_el_limite_de_pedidos_es_por_evento(cliente_con_base, eventos):
    """Gastar la cuota de un evento no puede dejar sin subir a los de otro."""
    for _ in range(rutas_publico.MAXIMO_FIRMAS_POR_DISPOSITIVO):
        firmar_desde(cliente_con_base, DISPOSITIVO)
    # El otro evento está cerrado, así que su error tiene que ser el del cierre
    # y no el del límite: prueba que la cuota no se comparte.
    r = firmar_desde(cliente_con_base, DISPOSITIVO, codigo=CODIGO_CERRADO)
    afirmar_error(r, "EVENTO_CERRADO", 409)


def test_no_se_firma_si_el_dispositivo_ya_gasto_su_cupo(cliente_con_base, eventos, db):
    """Firmar igual dejaría la foto subida a Cloudinary sin figurar en ningún lado."""
    activo = eventos["activo"]
    for i in range(activo.max_fotos_por_dispositivo):
        pid = f"eventos/{CODIGO_ACTIVO}/cupo{i:02d}"
        db.add(Foto(evento_id=activo.id, public_id=pid, url=url_de(pid),
                    estado="pendiente", dispositivo_hash="lleno" + "0" * 27))
    db.commit()
    r = cliente_con_base.post(
        f"/api/e/{CODIGO_ACTIVO}/firma", json={"dispositivo_hash": "lleno" + "0" * 27}
    )
    afirmar_error(r, "LIMITE_ALCANZADO", 429)


# ─────────────────────────────────────────────────────────────
# Registro de foto — la regla 4
# ─────────────────────────────────────────────────────────────

def test_registrar_foto(cliente_con_base, eventos, db):
    r = cliente_con_base.post(f"/api/e/{CODIGO_ACTIVO}/fotos", json=cuerpo_foto())
    assert r.status_code == 201, r.text
    assert set(r.json().keys()) == {"id", "estado"}
    assert r.json()["estado"] == "pendiente", "nace pendiente: nada se proyecta sin aprobar"

    fila = db.scalar(select(Foto).where(Foto.id == r.json()["id"]))
    assert fila.evento_id == eventos["activo"].id
    assert fila.subida_en.tzinfo is not None, "timestamptz"


@pytest.mark.parametrize(
    "public_id_ajeno",
    [
        "eventos/ef56gh78/robada",          # carpeta de otro evento
        "eventos/otracosa/robada",          # carpeta inventada
        "otracarpeta/ab12cd34/robada",      # el código está, pero no de prefijo
        "robada",                           # sin carpeta
        "eventos/ab12cd34",                 # la carpeta sin archivo
        "eventos/ab12cd34/sub/carpeta",     # subcarpeta
        "eventos/ab12cd34x/robada",         # prefijo parecido
    ],
)
def test_public_id_de_otra_carpeta_es_rechazado(cliente_con_base, eventos, public_id_ajeno):
    """CRITERIO DE ACEPTACIÓN. Sin esto se puede proyectar cualquier imagen."""
    cuerpo = cuerpo_foto(public_id=public_id_ajeno, url=url_de(public_id_ajeno))
    afirmar_error(
        cliente_con_base.post(f"/api/e/{CODIGO_ACTIVO}/fotos", json=cuerpo),
        "PUBLIC_ID_AJENO",
        403,
    )


def test_una_foto_rechazada_no_queda_en_la_base(cliente_con_base, eventos, db):
    cuerpo = cuerpo_foto(public_id="eventos/ef56gh78/robada", url=url_de("eventos/ef56gh78/robada"))
    cliente_con_base.post(f"/api/e/{CODIGO_ACTIVO}/fotos", json=cuerpo)
    assert db.scalar(select(Foto).where(Foto.public_id == "eventos/ef56gh78/robada")) is None


@pytest.mark.parametrize(
    "url_mala",
    [
        "https://otrositio.com/imagen.jpg",
        "http://res.cloudinary.com/demo/image/upload/v1/eventos/ab12cd34/nueva01.jpg",
        "https://res.cloudinary.com/demo/video/upload/v1/eventos/ab12cd34/nueva01.mp4",
        "https://res.cloudinary.com/demo/raw/upload/v1/eventos/ab12cd34/nueva01.jpg",
        "https://res.cloudinary.com/demo/image/upload/v1/eventos/ab12cd34/nueva01.mp4",
        "https://res.cloudinary.com/demo/image/upload/v1/otracosa.jpg",
    ],
)
def test_url_que_no_corresponde_es_rechazada(cliente_con_base, eventos, url_mala):
    """El campo que se proyecta es `url`, no `public_id`: si se aceptara
    cualquiera, la verificación de carpeta quedaría sin efecto."""
    afirmar_error(
        cliente_con_base.post(f"/api/e/{CODIGO_ACTIVO}/fotos", json=cuerpo_foto(url=url_mala)),
        "ARCHIVO_INVALIDO",
        400,
    )


def test_no_se_puede_subir_a_un_evento_cerrado(cliente_con_base, eventos):
    cuerpo = cuerpo_foto(CODIGO_CERRADO, "intento")
    afirmar_error(
        cliente_con_base.post(f"/api/e/{CODIGO_CERRADO}/fotos", json=cuerpo),
        "EVENTO_CERRADO",
        409,
    )


def test_limite_por_dispositivo(cliente_con_base, eventos):
    disp = "t" * 32
    for i in range(10):
        r = cliente_con_base.post(
            f"/api/e/{CODIGO_ACTIVO}/fotos",
            json=cuerpo_foto(sufijo=f"cupo{i:02d}", dispositivo_hash=disp),
        )
        assert r.status_code == 201, r.text
    r = cliente_con_base.post(
        f"/api/e/{CODIGO_ACTIVO}/fotos",
        json=cuerpo_foto(sufijo="unamas", dispositivo_hash=disp),
    )
    afirmar_error(r, "LIMITE_ALCANZADO", 429)
    assert "10" in r.json()["error"]["mensaje"]


def test_con_una_sola_foto_el_limite_se_dice_en_singular(cliente_con_base, eventos, db):
    """"Ya mandaste tus 1 fotos" no se dice: con cupo 1, "Ya mandaste tu foto"."""
    activo = eventos["activo"]
    activo.max_fotos_por_dispositivo = 1
    db.commit()
    disp = "u" * 32
    primera = cliente_con_base.post(
        f"/api/e/{CODIGO_ACTIVO}/fotos", json=cuerpo_foto(sufijo="unica", dispositivo_hash=disp)
    )
    assert primera.status_code == 201, primera.text
    r = cliente_con_base.post(
        f"/api/e/{CODIGO_ACTIVO}/fotos", json=cuerpo_foto(sufijo="otra", dispositivo_hash=disp)
    )
    afirmar_error(r, "LIMITE_ALCANZADO", 429)
    assert r.json()["error"]["mensaje"] == "Ya mandaste tu foto. ¡Gracias!"


def test_las_rechazadas_cuentan_para_el_limite(cliente_con_base, eventos, db):
    """"Ya mandaste tus 10 fotos": se cuenta lo que mandó, no lo que le aprobaron."""
    activo = eventos["activo"]
    disp = "r" * 32
    for i in range(10):
        pid = f"eventos/{CODIGO_ACTIVO}/rech{i:02d}"
        db.add(Foto(evento_id=activo.id, public_id=pid, url=url_de(pid),
                    estado="rechazada", dispositivo_hash=disp))
    db.commit()
    r = cliente_con_base.post(
        f"/api/e/{CODIGO_ACTIVO}/fotos", json=cuerpo_foto(sufijo="unamas", dispositivo_hash=disp)
    )
    afirmar_error(r, "LIMITE_ALCANZADO", 429)


def test_reintentar_la_misma_foto_no_la_duplica(cliente_con_base, eventos, db):
    """"La foto llegó o no llegó, nunca queda a medias registrada"."""
    cuerpo = cuerpo_foto(sufijo="reintento")
    primera = cliente_con_base.post(f"/api/e/{CODIGO_ACTIVO}/fotos", json=cuerpo)
    segunda = cliente_con_base.post(f"/api/e/{CODIGO_ACTIVO}/fotos", json=cuerpo)
    assert primera.status_code == 201
    assert segunda.status_code == 201
    assert primera.json()["id"] == segunda.json()["id"]
    assert db.scalar(
        select(Foto).where(Foto.public_id == cuerpo["public_id"])
    ) is not None


def test_nombre_vacio_se_guarda_como_nulo(cliente_con_base, eventos, db):
    r = cliente_con_base.post(
        f"/api/e/{CODIGO_ACTIVO}/fotos",
        json=cuerpo_foto(sufijo="sinnombre", nombre_invitado="   "),
    )
    fila = db.scalar(select(Foto).where(Foto.id == r.json()["id"]))
    assert fila.nombre_invitado is None


# ─────────────────────────────────────────────────────────────
# Pantalla
# ─────────────────────────────────────────────────────────────

def test_pantalla(cliente_con_base, eventos):
    r = cliente_con_base.get(f"/api/pantalla/{TOKEN_ACTIVO}")
    assert r.status_code == 200
    cuerpo = r.json()
    assert set(cuerpo.keys()) == {"evento", "config"}
    assert set(cuerpo["evento"].keys()) == {"nombre", "codigo_publico", "estado"}
    assert set(cuerpo["config"].keys()) == {
        "segundos_por_foto", "intervalo_polling_ms", "maximo_buffer",
        "fondo", "transicion", "mostrar_nombre", "mostrar_qr",
    }
    assert "id" not in cuerpo["evento"], "regla 1"
    assert cuerpo["config"]["segundos_por_foto"] == 7, "sale de la fila del evento"


def test_la_pantalla_de_un_evento_cerrado_sigue_andando(cliente_con_base, eventos):
    r = cliente_con_base.get(f"/api/pantalla/{TOKEN_CERRADO}")
    assert r.status_code == 200
    assert r.json()["evento"]["estado"] == "cerrado"
    assert len(cliente_con_base.get(f"/api/pantalla/{TOKEN_CERRADO}/fotos").json()["fotos"]) == 2


def test_la_pantalla_de_un_borrador_no_anda(cliente_con_base, eventos):
    r = cliente_con_base.get(f"/api/pantalla/{TOKEN_BORRADOR}")
    afirmar_error(r, "EVENTO_BORRADOR", 404)


def test_token_inexistente(cliente_con_base, eventos):
    afirmar_error(cliente_con_base.get("/api/pantalla/noexiste"), "EVENTO_NO_ENCONTRADO", 404)


def test_la_pantalla_solo_ve_aprobadas(cliente_con_base, eventos, db):
    cuerpo = cliente_con_base.get(f"/api/pantalla/{TOKEN_ACTIVO}/fotos?desde=0").json()
    assert len(cuerpo["fotos"]) == 6, "6 aprobadas de 9 cargadas"
    ids = [f["id"] for f in cuerpo["fotos"]]
    aprobadas = {
        f.id for f in db.scalars(
            select(Foto).where(Foto.evento_id == eventos["activo"].id, Foto.estado == "aprobada")
        )
    }
    assert set(ids) == aprobadas


def test_arranque_en_frio_devuelve_las_ultimas_ascendentes(cliente_con_base, eventos):
    cuerpo = cliente_con_base.get(f"/api/pantalla/{TOKEN_ACTIVO}/fotos?desde=0&limite=3").json()
    ids = [f["id"] for f in cuerpo["fotos"]]
    assert len(ids) == 3
    assert ids == sorted(ids), "de la más vieja a la más nueva"

    todas = [
        f["id"] for f in
        cliente_con_base.get(f"/api/pantalla/{TOKEN_ACTIVO}/fotos?desde=0&limite=40").json()["fotos"]
    ]
    assert ids == todas[-3:], "las ÚLTIMAS tres, no las primeras"
    assert cuerpo["ultimo_id"] == ids[-1]


def test_desde_n_devuelve_solo_aprobadas_con_id_mayor(cliente_con_base, eventos):
    """CRITERIO DE ACEPTACIÓN."""
    todas = cliente_con_base.get(f"/api/pantalla/{TOKEN_ACTIVO}/fotos?desde=0").json()["fotos"]
    corte = todas[2]["id"]
    cuerpo = cliente_con_base.get(f"/api/pantalla/{TOKEN_ACTIVO}/fotos?desde={corte}").json()
    ids = [f["id"] for f in cuerpo["fotos"]]
    assert ids == [f["id"] for f in todas if f["id"] > corte]
    assert all(i > corte for i in ids)
    assert ids == sorted(ids)
    assert cuerpo["ultimo_id"] == todas[-1]["id"]


def test_sin_novedades_devuelve_el_desde_recibido(cliente_con_base, eventos):
    cuerpo = cliente_con_base.get(f"/api/pantalla/{TOKEN_ACTIVO}/fotos?desde=999999").json()
    assert cuerpo["fotos"] == []
    assert cuerpo["ultimo_id"] == 999999


def test_una_foto_recien_aprobada_aparece_en_el_siguiente_polling(cliente_con_base, eventos, db):
    ultimo = cliente_con_base.get(f"/api/pantalla/{TOKEN_ACTIVO}/fotos?desde=0").json()["ultimo_id"]
    pendiente = db.scalar(
        select(Foto).where(Foto.evento_id == eventos["activo"].id, Foto.estado == "pendiente")
    )
    pendiente.estado = "aprobada"
    db.commit()

    cuerpo = cliente_con_base.get(f"/api/pantalla/{TOKEN_ACTIVO}/fotos?desde={ultimo}").json()
    assert [f["id"] for f in cuerpo["fotos"]] == [pendiente.id]


# ─────────────────────────────────────────────────────────────
# Aislamiento entre eventos
# ─────────────────────────────────────────────────────────────

def test_el_token_de_un_evento_no_muestra_fotos_del_otro(cliente_con_base, eventos, db):
    """Con el token del evento A no aparece ni una foto del evento B."""
    del_activo = cliente_con_base.get(f"/api/pantalla/{TOKEN_ACTIVO}/fotos?desde=0").json()["fotos"]
    del_cerrado = cliente_con_base.get(f"/api/pantalla/{TOKEN_CERRADO}/fotos?desde=0").json()["fotos"]

    ids_activo = {f["id"] for f in del_activo}
    ids_cerrado = {f["id"] for f in del_cerrado}
    assert ids_activo and ids_cerrado
    assert ids_activo.isdisjoint(ids_cerrado)

    # Se comprueba contra la carpeta del public_id, que es lo que ata una foto a
    # su evento. La URL no sirve para esto: apunta a la nube demo de Cloudinary.
    for ids, codigo in ((ids_activo, CODIGO_ACTIVO), (ids_cerrado, CODIGO_CERRADO)):
        carpetas = db.scalars(select(Foto.public_id).where(Foto.id.in_(ids))).all()
        assert all(p.startswith(f"eventos/{codigo}/") for p in carpetas)


def test_no_se_puede_subir_a_un_evento_con_el_codigo_de_otro(cliente_con_base, eventos, db):
    """Una foto pertenece a un solo evento y no se puede mover."""
    cuerpo = cuerpo_foto(CODIGO_ACTIVO, "mudanza")
    r = cliente_con_base.post(f"/api/e/{CODIGO_CERRADO}/fotos", json=cuerpo)
    assert r.status_code in (403, 409), r.text
    assert db.scalar(select(Foto).where(Foto.public_id == cuerpo["public_id"])) is None
