"""Endpoints de la pantalla de proyección. Base /api/pantalla.

FASE 1 — datos fijos. Los dos comportamientos de `desde` (arranque en frío y
polling incremental) sí están implementados de verdad sobre la lista fija: son
la semántica del contrato, y la Fase 7 construye `useCola.ts` contra esto.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from ..errores import Codigo, ErrorApp
from ..schemas import (
    ColaPantalla,
    FotoPantalla,
    Pantalla,
    PantallaConfig,
    PantallaEvento,
    RespuestaError,
)

router = APIRouter(prefix="/api/pantalla", tags=["pantalla"])

_BASE = "https://res.cloudinary.com/demo/image/upload"

# Los mismos tokens del seed (db/seed.sql).
_EVENTOS: dict[str, dict] = {
    "64syPN4YFgbJibLfIOlrjI51R0HFlKDm": {
        "nombre": "Casamiento Ana y Juan",
        "codigo_publico": "ab12cd34",
        "estado": "activo",
        "segundos_por_foto": 7,
    },
    "8MX4OqECds7IhkCmlK7vub76PntouGz1": {
        "nombre": "Cumple de 15 de Malena",
        "codigo_publico": "ef56gh78",
        "estado": "cerrado",
        "segundos_por_foto": 6,
    },
}

# Doce aprobadas, en orden ascendente de id. Verticales, horizontales,
# panorámicas y cuadradas, con nombres con acentos, uno vacío y algunos nulos:
# los casos que rompen el maquetado.
_APROBADAS: dict[str, list[dict]] = {
    "ab12cd34": [
        {"id": 101, "img": "couple",       "ancho": 1600, "alto": 1200, "nombre_invitado": "Sofía"},
        {"id": 102, "img": "sample",       "ancho": 1200, "alto": 1600, "nombre_invitado": "Martín Peña"},
        {"id": 103, "img": "balloons",     "ancho": 1600, "alto":  600, "nombre_invitado": "Sofía"},
        {"id": 104, "img": "cld-sample",   "ancho": 1600, "alto": 1200, "nombre_invitado": None},
        {"id": 105, "img": "flower",       "ancho": 1200, "alto": 1200, "nombre_invitado": "Martín Peña"},
        {"id": 106, "img": "lady",         "ancho": 1200, "alto": 1600, "nombre_invitado": ""},
        {"id": 107, "img": "horses",       "ancho": 1600, "alto":  600, "nombre_invitado": "Ñoño Gutiérrez"},
        {"id": 108, "img": "cld-sample-2", "ancho": 1200, "alto": 1600, "nombre_invitado": "Martín Peña"},
        {"id": 109, "img": "yellow_tulip", "ancho": 1200, "alto": 1600, "nombre_invitado": None},
        {"id": 110, "img": "sheep",        "ancho": 1600, "alto": 1200, "nombre_invitado": "Sofía"},
        {"id": 111, "img": "brown_sheep",  "ancho": 1200, "alto": 1600, "nombre_invitado": "Agustín Iñíguez"},
        {"id": 112, "img": "nice_couple",  "ancho": 1600, "alto": 1200, "nombre_invitado": "Malén Ibáñez"},
    ],
    "ef56gh78": [
        {"id": 201, "img": "sample",   "ancho": 1600, "alto": 1200, "nombre_invitado": "Malena"},
        {"id": 202, "img": "balloons", "ancho": 1200, "alto": 1600, "nombre_invitado": "Tía Coca"},
        {"id": 203, "img": "flower",   "ancho": 1600, "alto":  600, "nombre_invitado": None},
    ],
}

_ERROR_404 = {404: {"model": RespuestaError, "description": "EVENTO_NO_ENCONTRADO"}}


def _buscar_evento(token_pantalla: str) -> dict:
    evento = _EVENTOS.get(token_pantalla)
    if evento is None:
        raise ErrorApp(Codigo.EVENTO_NO_ENCONTRADO)
    return evento


def _armar(fila: dict, codigo_publico: str) -> FotoPantalla:
    sufijo = "" if codigo_publico == "ab12cd34" else "l_text:Arial_140_bold:EVENTO-B,co_white,g_north,y_60/"
    return FotoPantalla(
        id=fila["id"],
        url=f"{_BASE}/c_fill,w_{fila['ancho']},h_{fila['alto']}/{sufijo}{fila['img']}.jpg",
        ancho=fila["ancho"],
        alto=fila["alto"],
        nombre_invitado=fila["nombre_invitado"],
    )


@router.get(
    "/{token_pantalla}",
    response_model=Pantalla,
    responses={**_ERROR_404},
    summary="Configuración de la pantalla",
)
def obtener_pantalla(token_pantalla: str) -> Pantalla:
    """Un evento `cerrado` sigue sirviendo la pantalla: las aprobadas terminan de pasar."""
    evento = _buscar_evento(token_pantalla)
    if evento["estado"] == "borrador":
        raise ErrorApp(Codigo.EVENTO_BORRADOR)
    return Pantalla(
        evento=PantallaEvento(
            nombre=evento["nombre"],
            codigo_publico=evento["codigo_publico"],
            estado=evento["estado"],
        ),
        config=PantallaConfig(
            segundos_por_foto=evento["segundos_por_foto"],
            intervalo_polling_ms=6000,
            maximo_buffer=200,
        ),
    )


@router.get(
    "/{token_pantalla}/fotos",
    response_model=ColaPantalla,
    responses={**_ERROR_404},
    summary="Fotos aprobadas, incremental",
)
def obtener_fotos(
    token_pantalla: str,
    desde: int = Query(default=0, ge=0, description="0 arranca en frío; N devuelve las de id > N"),
    limite: int = Query(default=40, ge=1, le=200),
) -> ColaPantalla:
    """Devuelve **sólo fotos aprobadas**, siempre en orden ascendente de id."""
    evento = _buscar_evento(token_pantalla)
    if evento["estado"] == "borrador":
        raise ErrorApp(Codigo.EVENTO_BORRADOR)

    todas = _APROBADAS.get(evento["codigo_publico"], [])
    if desde == 0:
        # Arranque en frío: las últimas `limite`, de la más vieja a la más nueva.
        elegidas = todas[-limite:]
    else:
        # Polling normal: sólo lo nuevo.
        elegidas = [f for f in todas if f["id"] > desde][:limite]

    fotos = [_armar(f, evento["codigo_publico"]) for f in elegidas]
    return ColaPantalla(
        fotos=fotos,
        ultimo_id=fotos[-1].id if fotos else desde,
    )
