"""Endpoints públicos: los usa el celular del invitado. Base /api/e.

El invitado no tiene cuenta ni login. Se lo identifica por `dispositivo_hash`,
que genera el navegador y guarda, sin pedirle ningún dato.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..cloudinary_service import firmar, verificar_public_id, verificar_url
from ..database import get_db
from ..deps import evento_por_codigo
from ..errores import Codigo, ErrorApp
from ..models import Evento, Foto
from ..ratelimit import limpiar_vencidos, permitido
from ..schemas import (
    EventoPublico,
    Firma,
    FotoNueva,
    FotoRegistrada,
    PedidoFirma,
    RespuestaError,
)

router = APIRouter(prefix="/api/e", tags=["público"])

_ERROR_404 = {404: {"model": RespuestaError, "description": "EVENTO_NO_ENCONTRADO"}}
_ERROR_409 = {409: {"model": RespuestaError, "description": "EVENTO_CERRADO"}}
_ERROR_429 = {429: {"model": RespuestaError, "description": "LIMITE_ALCANZADO · DEMASIADOS_PEDIDOS"}}


def _ip_del_pedido(request: Request) -> str:
    """Detrás del proxy de Render, request.client.host es el proxy."""
    reenviada = request.headers.get("x-forwarded-for")
    if reenviada:
        return reenviada.split(",")[0].strip()
    return request.client.host if request.client else "desconocida"


def _exigir_abierto(evento: Evento) -> None:
    """Un evento cerrado rechaza subidas nuevas, pero sigue sirviendo la pantalla."""
    if evento.estado == "cerrado":
        raise ErrorApp(Codigo.EVENTO_CERRADO)


def _fotos_del_dispositivo(db: Session, evento: Evento, dispositivo_hash: str) -> int:
    return db.scalar(
        select(func.count())
        .select_from(Foto)
        .where(Foto.evento_id == evento.id, Foto.dispositivo_hash == dispositivo_hash)
    ) or 0


def _exigir_cupo(db: Session, evento: Evento, dispositivo_hash: str) -> None:
    """Cuenta TODAS las fotos del dispositivo, también las rechazadas.

    El texto que ve el invitado es "Ya mandaste tus 10 fotos": lo que se cuenta
    es lo que mandó, no lo que le aprobaron. Además, no contar las rechazadas
    dejaría mandar fotos malas sin tope.
    """
    if _fotos_del_dispositivo(db, evento, dispositivo_hash) >= evento.max_fotos_por_dispositivo:
        raise ErrorApp(
            Codigo.LIMITE_ALCANZADO,
            f"Ya mandaste tus {evento.max_fotos_por_dispositivo} fotos. ¡Gracias!",
        )


@router.get(
    "/{codigo_publico}",
    response_model=EventoPublico,
    responses={**_ERROR_404},
    summary="Datos del evento para la app del invitado",
)
def obtener_evento(evento: Evento = Depends(evento_por_codigo)) -> EventoPublico:
    """Devuelve `estado` también cuando es `cerrado`, para que la app muestre la
    pantalla de cierre. Un evento en `borrador` responde 404: sin publicar no
    existe hacia afuera."""
    return EventoPublico(
        nombre=evento.nombre,
        fecha_evento=evento.fecha_evento,
        estado=evento.estado,
        max_fotos_por_dispositivo=evento.max_fotos_por_dispositivo,
    )


@router.post(
    "/{codigo_publico}/firma",
    response_model=Firma,
    responses={**_ERROR_404, **_ERROR_409, **_ERROR_429},
    summary="Firma para subir directo a Cloudinary",
)
def firmar_subida(
    request: Request,
    pedido: PedidoFirma,
    evento: Evento = Depends(evento_por_codigo),
    db: Session = Depends(get_db),
) -> Firma:
    _exigir_abierto(evento)

    if not permitido(_ip_del_pedido(request), evento.codigo_publico):
        raise ErrorApp(Codigo.DEMASIADOS_PEDIDOS)
    limpiar_vencidos()

    # Se comprueba el cupo ANTES de firmar: sin esto se le entrega una firma
    # válida a alguien que después va a ser rechazado, y la foto queda subida a
    # Cloudinary ocupando lugar sin figurar en ninguna parte.
    _exigir_cupo(db, evento, pedido.dispositivo_hash)

    return Firma(**firmar(evento.codigo_publico))


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
def registrar_foto(
    foto: FotoNueva,
    evento: Evento = Depends(evento_por_codigo),
    db: Session = Depends(get_db),
) -> FotoRegistrada:
    _exigir_abierto(evento)

    # Regla 4. Va primero: es la que impide proyectar una imagen ajena.
    verificar_public_id(foto.public_id, evento.codigo_publico)
    verificar_url(foto.url, foto.public_id)

    _exigir_cupo(db, evento, foto.dispositivo_hash)

    nombre = (foto.nombre_invitado or "").strip() or None
    fila = Foto(
        evento_id=evento.id,
        public_id=foto.public_id,
        url=foto.url,
        ancho=foto.ancho,
        alto=foto.alto,
        bytes=foto.bytes,
        estado="pendiente",
        dispositivo_hash=foto.dispositivo_hash,
        nombre_invitado=nombre,
    )
    db.add(fila)
    try:
        db.commit()
    except IntegrityError:
        # public_id repetido: el navegador reintentó después de que la primera
        # llamada llegó igual. Se devuelve la foto que ya existe en vez de un
        # error: "la foto llegó o no llegó, nunca queda a medias registrada".
        db.rollback()
        existente = db.scalar(select(Foto).where(Foto.public_id == foto.public_id))
        if existente is not None and existente.evento_id == evento.id:
            return FotoRegistrada(id=existente.id, estado=existente.estado)
        raise ErrorApp(Codigo.PUBLIC_ID_AJENO) from None

    db.refresh(fila)
    return FotoRegistrada(id=fila.id, estado=fila.estado)
