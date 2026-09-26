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
from ..ratelimit import ip_del_pedido, limpiar_cada_tanto, permitido_en_todas
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

# Topes de firmas, cada 10 minutos y por evento. En un salón todos los invitados
# comparten el wifi y salen por la misma IP pública: con un tope por IP solo, a
# los 30 pedidos se bloqueaba a todo el salón. Por eso la cuenta fina es por
# celular (IP + dispositivo_hash), y la de la conexión entera queda como un
# techo alto que sólo frena a un script que inventa un dispositivo por pedido.
# El máximo de fotos por celular del evento sigue valiendo aparte.
MAXIMO_FIRMAS_POR_DISPOSITIVO = 30
MAXIMO_FIRMAS_POR_CONEXION = 600

# El registro de una foto lleva el mismo par de topes, en cuentas aparte. No
# alcanza con los de la firma: /fotos no exige haber pedido una, y el cupo por
# celular cuenta por un dispositivo_hash que elige el cliente. Sin esto, desde
# una sola conexión y rotando el hash se llenaba la bandeja de pendientes. A un
# invitado real no lo frena nunca: cada foto suya ya pasó por una firma, que
# tiene los mismos números.
MAXIMO_REGISTROS_POR_DISPOSITIVO = MAXIMO_FIRMAS_POR_DISPOSITIVO
MAXIMO_REGISTROS_POR_CONEXION = MAXIMO_FIRMAS_POR_CONEXION
# Primer elemento de las claves de /fotos. Una IP nunca se llama así, así que
# no comparten cuenta con las de la firma, que empiezan por la IP.
_CLAVE_FOTOS = "fotos"


def _exigir_abierto(evento: Evento) -> None:
    """Un evento cerrado rechaza subidas nuevas, pero sigue sirviendo la pantalla.

    Uno con las fotos ya borradas de Cloudinary también, aunque figure abierto:
    la limpieza lo cierra al borrar, y el panel no lo deja reabrir, pero una
    foto que entrara después quedaría en Cloudinary para siempre.
    """
    if evento.estado == "cerrado" or evento.fotos_borradas_en is not None:
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
        raise ErrorApp(Codigo.LIMITE_ALCANZADO, _mensaje_de_cupo(evento.max_fotos_por_dispositivo))


def _mensaje_de_cupo(maximo: int) -> str:
    """Con una sola foto por invitado, "Ya mandaste tus 1 fotos" no se dice."""
    if maximo == 1:
        return "Ya mandaste tu foto. ¡Gracias!"
    return f"Ya mandaste tus {maximo} fotos. ¡Gracias!"


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

    # Las dos cuentas se anotan juntas o ninguna: un celular que insiste después
    # de su tope no le gasta lugar al resto del salón.
    ip = ip_del_pedido(request)
    if not permitido_en_todas([
        ((ip, evento.codigo_publico, pedido.dispositivo_hash), MAXIMO_FIRMAS_POR_DISPOSITIVO),
        ((ip, evento.codigo_publico), MAXIMO_FIRMAS_POR_CONEXION),
    ]):
        raise ErrorApp(Codigo.DEMASIADOS_PEDIDOS)
    limpiar_cada_tanto()

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
    request: Request,
    foto: FotoNueva,
    evento: Evento = Depends(evento_por_codigo),
    db: Session = Depends(get_db),
) -> FotoRegistrada:
    """El largo de `public_id` y de `url` lo acota FotoNueva: sin tope, una url
    de un mega entraba entera a la base, y un public_id de miles de caracteres
    rompía el índice único con un 500 fuera del contrato."""
    _exigir_abierto(evento)

    # Regla 4. Va primero: es la que impide proyectar una imagen ajena.
    verificar_public_id(foto.public_id, evento.codigo_publico)
    verificar_url(foto.url, foto.public_id)

    ip = ip_del_pedido(request)
    if not permitido_en_todas([
        ((_CLAVE_FOTOS, ip, evento.codigo_publico, foto.dispositivo_hash),
         MAXIMO_REGISTROS_POR_DISPOSITIVO),
        ((_CLAVE_FOTOS, ip, evento.codigo_publico), MAXIMO_REGISTROS_POR_CONEXION),
    ]):
        raise ErrorApp(Codigo.DEMASIADOS_PEDIDOS)
    limpiar_cada_tanto()

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
