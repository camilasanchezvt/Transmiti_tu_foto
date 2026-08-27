"""Fase 4: moderación, lote, resumen y descarga.

Criterio de aceptación del brief: aprobar dos veces la misma foto no cambia nada
la segunda vez, y la descarga de un evento con las veinte fotos del seed produce
un ZIP que abre bien.

Necesitan Postgres. Definí DATABASE_URL_TEST o se saltean solas.
"""

from __future__ import annotations

import io
import zipfile

import pytest
from sqlalchemy import select

from app.models import Administrador, Evento, Foto
from app.security import hashear_password
from tests.conftest import CODIGO_ACTIVO, sin_base, url_de

pytestmark = sin_base


def afirmar_error(respuesta, codigo_esperado: str, http_esperado: int) -> None:
    assert respuesta.status_code == http_esperado, respuesta.text
    assert respuesta.json()["error"]["codigo"] == codigo_esperado


def ids_por_estado(cliente, id_evento: int, estado: str) -> list[int]:
    r = cliente.get(f"/api/admin/eventos/{id_evento}/fotos?estado={estado}&limite=200")
    return [f["id"] for f in r.json()["fotos"]]


# ─────────────────────────────────────────────────────────────
# Resumen
# ─────────────────────────────────────────────────────────────

def test_resumen(autorizado, eventos):
    r = autorizado.get(f"/api/admin/eventos/{eventos['activo'].id}/resumen")
    assert r.status_code == 200
    assert r.json() == {"pendientes": 2, "aprobadas": 6, "rechazadas": 1}


def test_resumen_de_evento_ajeno(autorizado, eventos, db):
    otro = Administrador(email="otro@t.test", nombre="Otro",
                         password_hash=hashear_password("clave-larga-cualquiera"))
    db.add(otro)
    db.commit()
    ajeno = Evento(admin_id=otro.id, nombre="Ajeno", fecha_evento="2026-12-02",
                   codigo_publico="zz99yy88", token_pantalla="Z" * 32, estado="activo")
    db.add(ajeno)
    db.commit()
    afirmar_error(
        autorizado.get(f"/api/admin/eventos/{ajeno.id}/resumen"), "EVENTO_NO_ENCONTRADO", 404
    )


# ─────────────────────────────────────────────────────────────
# Listado de fotos para la bandeja
# ─────────────────────────────────────────────────────────────

def test_listar_fotos_por_estado(autorizado, eventos):
    id_evento = eventos["activo"].id
    assert len(ids_por_estado(autorizado, id_evento, "pendiente")) == 2
    assert len(ids_por_estado(autorizado, id_evento, "aprobada")) == 6
    assert len(ids_por_estado(autorizado, id_evento, "rechazada")) == 1


def test_listar_fotos_sin_filtro_las_trae_todas(autorizado, eventos):
    r = autorizado.get(f"/api/admin/eventos/{eventos['activo'].id}/fotos?limite=200")
    assert len(r.json()["fotos"]) == 9


def test_listar_fotos_es_incremental(autorizado, eventos):
    """El auto-refresco pide sólo lo nuevo, sin reordenar lo que se está mirando."""
    id_evento = eventos["activo"].id
    todas = autorizado.get(f"/api/admin/eventos/{id_evento}/fotos?limite=200").json()
    corte = todas["fotos"][3]["id"]
    nuevas = autorizado.get(
        f"/api/admin/eventos/{id_evento}/fotos?desde={corte}&limite=200"
    ).json()
    assert all(f["id"] > corte for f in nuevas["fotos"])
    assert [f["id"] for f in nuevas["fotos"]] == sorted(f["id"] for f in nuevas["fotos"])
    assert nuevas["ultimo_id"] == todas["fotos"][-1]["id"]


def test_estado_inexistente_es_datos_invalidos(autorizado, eventos):
    r = autorizado.get(f"/api/admin/eventos/{eventos['activo'].id}/fotos?estado=inventado")
    afirmar_error(r, "DATOS_INVALIDOS", 422)


# ─────────────────────────────────────────────────────────────
# Moderación de a una — la idempotencia
# ─────────────────────────────────────────────────────────────

def test_aprobar_dos_veces_no_cambia_nada_la_segunda(autorizado, eventos, db):
    """CRITERIO DE ACEPTACIÓN."""
    id_foto = ids_por_estado(autorizado, eventos["activo"].id, "pendiente")[0]

    primera = autorizado.patch(f"/api/admin/fotos/{id_foto}", json={"estado": "aprobada"})
    assert primera.status_code == 200
    assert primera.json() == {"id": id_foto, "estado": "aprobada"}

    db.expire_all()
    marca = db.scalar(select(Foto.moderada_en).where(Foto.id == id_foto))
    quien = db.scalar(select(Foto.moderada_por).where(Foto.id == id_foto))
    assert marca is not None and quien is not None

    segunda = autorizado.patch(f"/api/admin/fotos/{id_foto}", json={"estado": "aprobada"})
    assert segunda.status_code == 200
    assert segunda.json() == primera.json()

    db.expire_all()
    assert db.scalar(select(Foto.moderada_en).where(Foto.id == id_foto)) == marca, \
        "ni siquiera se vuelve a sellar la marca de moderación"


def test_moderar_no_crea_ni_borra_filas(autorizado, eventos, db):
    """Nada se borra: rechazar es un estado, no un DELETE."""
    id_evento = eventos["activo"].id
    antes = db.scalar(select(Foto.id).where(Foto.evento_id == id_evento).order_by(Foto.id))
    total_antes = len(db.scalars(select(Foto).where(Foto.evento_id == id_evento)).all())

    autorizado.patch(f"/api/admin/fotos/{antes}", json={"estado": "rechazada"})
    db.expire_all()

    total_despues = len(db.scalars(select(Foto).where(Foto.evento_id == id_evento)).all())
    assert total_antes == total_despues
    assert db.scalar(select(Foto.estado).where(Foto.id == antes)) == "rechazada"


def test_se_puede_revertir_un_rechazo(autorizado, eventos):
    """Es la red de seguridad de la tecla Z del panel."""
    id_foto = ids_por_estado(autorizado, eventos["activo"].id, "pendiente")[0]
    autorizado.patch(f"/api/admin/fotos/{id_foto}", json={"estado": "rechazada"})
    r = autorizado.patch(f"/api/admin/fotos/{id_foto}", json={"estado": "pendiente"})
    assert r.json() == {"id": id_foto, "estado": "pendiente"}


def test_no_se_puede_moderar_una_foto_ajena(autorizado, eventos, db):
    otro = Administrador(email="otro2@t.test", nombre="Otro",
                         password_hash=hashear_password("clave-larga-cualquiera"))
    db.add(otro)
    db.commit()
    ajeno = Evento(admin_id=otro.id, nombre="Ajeno", fecha_evento="2026-12-02",
                   codigo_publico="yy88xx77", token_pantalla="Y" * 32, estado="activo")
    db.add(ajeno)
    db.commit()
    foto = Foto(evento_id=ajeno.id, public_id="eventos/yy88xx77/a", url=url_de("x"),
                estado="pendiente")
    db.add(foto)
    db.commit()

    afirmar_error(
        autorizado.patch(f"/api/admin/fotos/{foto.id}", json={"estado": "aprobada"}),
        "FOTO_NO_ENCONTRADA", 404,
    )
    db.expire_all()
    assert db.scalar(select(Foto.estado).where(Foto.id == foto.id)) == "pendiente"


def test_foto_inexistente(autorizado, eventos):
    afirmar_error(
        autorizado.patch("/api/admin/fotos/999999", json={"estado": "aprobada"}),
        "FOTO_NO_ENCONTRADA", 404,
    )


# ─────────────────────────────────────────────────────────────
# Lote
# ─────────────────────────────────────────────────────────────

def test_lote_aprueba_todas_de_una(autorizado, eventos):
    id_evento = eventos["activo"].id
    pendientes = ids_por_estado(autorizado, id_evento, "pendiente")
    r = autorizado.post("/api/admin/fotos/lote", json={"ids": pendientes, "estado": "aprobada"})
    assert r.status_code == 200
    assert r.json() == {"afectadas": len(pendientes)}
    assert ids_por_estado(autorizado, id_evento, "pendiente") == []


def test_repetir_el_lote_no_afecta_nada(autorizado, eventos):
    """Misma idempotencia que la moderación de a una."""
    pendientes = ids_por_estado(autorizado, eventos["activo"].id, "pendiente")
    autorizado.post("/api/admin/fotos/lote", json={"ids": pendientes, "estado": "aprobada"})
    r = autorizado.post("/api/admin/fotos/lote", json={"ids": pendientes, "estado": "aprobada"})
    assert r.json() == {"afectadas": 0}


def test_el_lote_ignora_ids_ajenos_pero_modera_los_propios(autorizado, eventos, db):
    """Un id ajeno en la lista no puede impedir que se moderen los propios."""
    otro = Administrador(email="otro3@t.test", nombre="Otro",
                         password_hash=hashear_password("clave-larga-cualquiera"))
    db.add(otro)
    db.commit()
    ajeno = Evento(admin_id=otro.id, nombre="Ajeno", fecha_evento="2026-12-02",
                   codigo_publico="xx77ww66", token_pantalla="X" * 32, estado="activo")
    db.add(ajeno)
    db.commit()
    foto_ajena = Foto(evento_id=ajeno.id, public_id="eventos/xx77ww66/a", url=url_de("x"),
                      estado="pendiente")
    db.add(foto_ajena)
    db.commit()

    propias = ids_por_estado(autorizado, eventos["activo"].id, "pendiente")
    r = autorizado.post(
        "/api/admin/fotos/lote", json={"ids": propias + [foto_ajena.id], "estado": "aprobada"}
    )
    assert r.json() == {"afectadas": len(propias)}
    db.expire_all()
    assert db.scalar(select(Foto.estado).where(Foto.id == foto_ajena.id)) == "pendiente"


def test_lote_vacio_es_rechazado(autorizado, eventos):
    afirmar_error(
        autorizado.post("/api/admin/fotos/lote", json={"ids": [], "estado": "aprobada"}),
        "DATOS_INVALIDOS", 422,
    )


# ─────────────────────────────────────────────────────────────
# Cierre del evento
# ─────────────────────────────────────────────────────────────

def test_cerrar_un_evento(autorizado, eventos, db):
    id_evento = eventos["activo"].id
    r = autorizado.patch(f"/api/admin/eventos/{id_evento}", json={"estado": "cerrado"})
    assert r.status_code == 200
    assert r.json()["estado"] == "cerrado"
    db.expire_all()
    assert db.scalar(select(Evento.cerrado_en).where(Evento.id == id_evento)) is not None


def test_un_evento_cerrado_no_acepta_fotos_pero_su_pantalla_sigue(autorizado, eventos):
    id_evento = eventos["activo"].id
    autorizado.patch(f"/api/admin/eventos/{id_evento}", json={"estado": "cerrado"})

    subida = autorizado.post(
        f"/api/e/{CODIGO_ACTIVO}/firma", json={"dispositivo_hash": "d" * 32}
    )
    afirmar_error(subida, "EVENTO_CERRADO", 409)

    pantalla = autorizado.get(f"/api/pantalla/{eventos['activo'].token_pantalla}/fotos")
    assert pantalla.status_code == 200
    assert len(pantalla.json()["fotos"]) == 6, "las aprobadas siguen pasando"


def test_reabrir_borra_la_marca_de_cierre(autorizado, eventos, db):
    id_evento = eventos["activo"].id
    autorizado.patch(f"/api/admin/eventos/{id_evento}", json={"estado": "cerrado"})
    autorizado.patch(f"/api/admin/eventos/{id_evento}", json={"estado": "activo"})
    db.expire_all()
    assert db.scalar(select(Evento.cerrado_en).where(Evento.id == id_evento)) is None


# ─────────────────────────────────────────────────────────────
# Descarga
# ─────────────────────────────────────────────────────────────

def test_el_zip_abre_bien_y_trae_las_aprobadas(autorizado, eventos):
    """CRITERIO DE ACEPTACIÓN. Las URLs del fixture son de Cloudinary de verdad."""
    r = autorizado.get(f"/api/admin/eventos/{eventos['activo'].id}/descarga?incluir=aprobadas")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"

    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        assert z.testzip() is None, "el ZIP está sano"
        nombres = z.namelist()
        assert len(nombres) == 6
        for nombre in nombres:
            assert z.read(nombre)[:2] == b"\xff\xd8", f"{nombre} no es un JPEG"


def test_el_zip_de_todas_incluye_las_rechazadas(autorizado, eventos):
    r = autorizado.get(f"/api/admin/eventos/{eventos['activo'].id}/descarga?incluir=todas")
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        assert len(z.namelist()) == 9


def test_el_zip_se_llama_con_el_evento_y_la_fecha(autorizado, eventos):
    """Se compara el nombre entero y no por partes: buscar el id como subcadena
    da falso positivo porque el «1» del id aparece dentro de la fecha."""
    from urllib.parse import unquote

    r = autorizado.get(f"/api/admin/eventos/{eventos['activo'].id}/descarga")
    disposicion = r.headers["content-disposition"]
    assert disposicion.startswith("attachment; filename*=UTF-8''")
    nombre = unquote(disposicion.split("''", 1)[1])
    assert nombre == "Casamiento Ana y Juan - 2026-09-12.zip"


def test_los_nombres_de_adentro_llevan_el_invitado(autorizado, eventos):
    r = autorizado.get(f"/api/admin/eventos/{eventos['activo'].id}/descarga?incluir=aprobadas")
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        nombres = z.namelist()
    assert all(n[:3].isdigit() for n in nombres), "numerados, para que no se reordenen"
    assert any("Invitado" in n for n in nombres)
    assert not any("/" in n or chr(92) in n for n in nombres), "sin carpetas adentro"


def test_una_url_rota_no_tira_abajo_la_descarga(autorizado, eventos, db):
    """Con doscientas fotos, que una URL falle no puede arruinar el ZIP entero."""
    rota = db.scalar(
        select(Foto).where(Foto.evento_id == eventos["activo"].id, Foto.estado == "aprobada")
    )
    rota.url = "https://res.cloudinary.com/demo/image/upload/v1/no-existe-nada-aca.jpg"
    db.commit()

    r = autorizado.get(f"/api/admin/eventos/{eventos['activo'].id}/descarga?incluir=aprobadas")
    assert r.status_code == 200
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        assert z.testzip() is None
        assert len(z.namelist()) == 5, "las otras cinco llegaron igual"


def test_el_zip_se_arma_en_streaming(eventos):
    """El ZIP sale de a pedazos y nunca está entero en memoria.

    Se prueba el generador directamente y no la respuesta HTTP: el cliente de
    pruebas junta los pedazos antes de entregarlos, así que por ahí la propiedad
    no se puede observar aunque se cumpla.

    Con doscientas fotos de 300 KB, juntarlo entero serían 60 MB retenidos
    mientras dura la descarga, y Render gratuito se queda sin memoria.
    """
    from app.cloudinary_service import armar_zip
    from tests.conftest import url_real

    fotos = [(f"Invitado {i}", url_real(i)) for i in range(6)]

    pedazos, acumulado, maximo_retenido = 0, 0, 0
    for pedazo in armar_zip(fotos):
        pedazos += 1
        acumulado += len(pedazo)
        maximo_retenido = max(maximo_retenido, len(pedazo))

    assert pedazos > 6, "tiene que salir de a pedazos, no uno por foto ni uno solo"
    assert acumulado > 0
    assert maximo_retenido < acumulado, "ningún pedazo contiene el ZIP entero"


def test_descarga_de_evento_ajeno(autorizado, eventos, db):
    otro = Administrador(email="otro4@t.test", nombre="Otro",
                         password_hash=hashear_password("clave-larga-cualquiera"))
    db.add(otro)
    db.commit()
    ajeno = Evento(admin_id=otro.id, nombre="Ajeno", fecha_evento="2026-12-02",
                   codigo_publico="vv55uu44", token_pantalla="V" * 32, estado="activo")
    db.add(ajeno)
    db.commit()
    afirmar_error(
        autorizado.get(f"/api/admin/eventos/{ajeno.id}/descarga"), "EVENTO_NO_ENCONTRADO", 404
    )


def test_incluir_invalido_es_rechazado(autorizado, eventos):
    r = autorizado.get(f"/api/admin/eventos/{eventos['activo'].id}/descarga?incluir=cualquiera")
    afirmar_error(r, "DATOS_INVALIDOS", 422)
