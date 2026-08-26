"""Endpoints públicos: los usa el celular del invitado. Base /api/e.

FASE 1 — los datos son fijos, escritos a mano. No hay base ni Cloudinary.
Para que los errores se puedan probar de verdad, los códigos conocidos
devuelven el camino feliz y cualquier otro devuelve EVENTO_NO_ENCONTRADO.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, status

from ..errores import Codigo, ErrorApp
from ..schemas import (
    EventoPublico,
    Firma,
    FotoNueva,
    FotoRegistrada,
    PedidoFirma,
    RespuestaError,
)

router = APIRouter(prefix="/api/e", tags=["público"])

# ── Datos fijos de la Fase 1 ────────────────────────────────
# Copian a propósito los códigos del seed (db/seed.sql) para que el frontend
# que se construya contra esta fase siga andando contra el backend real.
_EVENTOS: dict[str, dict] = {
    "ab12cd34": {
        "nombre": "Casamiento Ana y Juan",
        "fecha_evento": date(2026, 9, 12),
        "estado": "activo",
        "max_fotos_por_dispositivo": 10,
    },
    "ef56gh78": {
        "nombre": "Cumple de 15 de Malena",
        "fecha_evento": date(2026, 7, 4),
        "estado": "cerrado",
        "max_fotos_por_dispositivo": 10,
    },
}

_ERROR_404 = {404: {"model": RespuestaError, "description": "EVENTO_NO_ENCONTRADO"}}
_ERROR_409 = {409: {"model": RespuestaError, "description": "EVENTO_CERRADO"}}
_ERROR_429 = {429: {"model": RespuestaError, "description": "LIMITE_ALCANZADO · DEMASIADOS_PEDIDOS"}}


def _buscar_evento(codigo_publico: str) -> dict:
    evento = _EVENTOS.get(codigo_publico)
    if evento is None:
        raise ErrorApp(Codigo.EVENTO_NO_ENCONTRADO)
    return evento


@router.get(
    "/{codigo_publico}",
    response_model=EventoPublico,
    responses={**_ERROR_404},
    summary="Datos del evento para la app del invitado",
)
def obtener_evento(codigo_publico: str) -> EventoPublico:
    """Un evento en `borrador` responde 404: sin publicar no existe hacia afuera."""
    evento = _buscar_evento(codigo_publico)
    if evento["estado"] == "borrador":
        raise ErrorApp(Codigo.EVENTO_NO_ENCONTRADO)
    return EventoPublico(**evento)


@router.post(
    "/{codigo_publico}/firma",
    response_model=Firma,
    responses={**_ERROR_404, **_ERROR_409, **_ERROR_429},
    summary="Firma para subir directo a Cloudinary",
)
def firmar_subida(codigo_publico: str, pedido: PedidoFirma) -> Firma:
    """Firma sólo `folder` y `timestamp`. La carpeta es `eventos/{codigo_publico}`."""
    evento = _buscar_evento(codigo_publico)
    if evento["estado"] == "cerrado":
        raise ErrorApp(Codigo.EVENTO_CERRADO)
    return Firma(
        cloud_name="demo",
        api_key="000000000000000",
        timestamp=1756200000,
        signature="0" * 40,
        folder=f"eventos/{codigo_publico}",
    )


@router.post(
    "/{codigo_publico}/fotos",
    response_model=FotoRegistrada,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": RespuestaError, "description": "ARCHIVO_INVALIDO"},
        403: {"model": RespuestaError, "description": "PUBLIC_ID_AJENO"},
        **_ERROR_404,
        **_ERROR_409,
        **_ERROR_429,
    },
    summary="Registrar una foto ya subida a Cloudinary",
)
def registrar_foto(codigo_publico: str, foto: FotoNueva) -> FotoRegistrada:
    """El `public_id` tiene que vivir dentro de la carpeta del evento (regla 4)."""
    evento = _buscar_evento(codigo_publico)
    if evento["estado"] == "cerrado":
        raise ErrorApp(Codigo.EVENTO_CERRADO)
    if not foto.public_id.startswith(f"eventos/{codigo_publico}/"):
        raise ErrorApp(Codigo.PUBLIC_ID_AJENO)
    return FotoRegistrada(id=128, estado="pendiente")
