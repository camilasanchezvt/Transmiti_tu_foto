"""Endpoints de la pantalla de proyección. Base /api/pantalla.

El token de pantalla sólo habilita a LEER las fotos aprobadas de su evento.
Todas las consultas se acotan por el evento que sale del token: de ahí sale el
aislamiento entre eventos simultáneos.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import vinculacion
from ..database import get_db
from ..deps import evento_por_token
from ..errores import Codigo, ErrorApp
from ..limpieza import archivos_vencidos
from ..models import Evento, Foto
from ..ratelimit import ip_del_pedido, limpiar_cada_tanto, permitido
from ..schemas import (
    ColaPantalla,
    FotoPantalla,
    Pantalla,
    PantallaConfig,
    PantallaEvento,
    PedidoCanje,
    RespuestaError,
    TokenDePantalla,
)

router = APIRouter(prefix="/api/pantalla", tags=["pantalla"])

# No son columnas de la tabla `eventos`: son constantes del servidor. De la base
# sale sólo `segundos_por_foto`.
INTERVALO_POLLING_MS = 6000
MAXIMO_BUFFER = 200

_ERROR_404 = {404: {"model": RespuestaError, "description": "EVENTO_NO_ENCONTRADO"}}


@router.get(
    "/{token_pantalla}",
    response_model=Pantalla,
    responses={**_ERROR_404},
    summary="Configuración de la pantalla",
)
def obtener_pantalla(evento: Evento = Depends(evento_por_token)) -> Pantalla:
    """Un evento `cerrado` sigue sirviendo la pantalla: las aprobadas terminan de pasar.

    Desde el día del borrado de sus archivos figura `cerrado` aunque la pasada
    de limpieza todavía no lo haya cerrado: sus fotos ya no se sirven (ver
    obtener_fotos), así que la pantalla muestra el cierre y no un QR que invita
    a mandar fotos que se borrarían enseguida.
    """
    return Pantalla(
        evento=PantallaEvento(
            nombre=evento.nombre,
            codigo_publico=evento.codigo_publico,
            estado="cerrado" if archivos_vencidos(evento) else evento.estado,
        ),
        config=PantallaConfig(
            segundos_por_foto=evento.segundos_por_foto,
            intervalo_polling_ms=INTERVALO_POLLING_MS,
            maximo_buffer=MAXIMO_BUFFER,
        ),
    )


@router.get(
    "/{token_pantalla}/fotos",
    response_model=ColaPantalla,
    responses={**_ERROR_404},
    summary="Fotos aprobadas, incremental",
)
def obtener_fotos(
    desde: int = Query(default=0, ge=0, description="0 arranca en frío; N devuelve las de id > N"),
    limite: int = Query(default=40, ge=1, le=200),
    evento: Evento = Depends(evento_por_token),
    db: Session = Depends(get_db),
) -> ColaPantalla:
    """Devuelve **sólo fotos aprobadas**, siempre ascendentes por id.

    Dos comportamientos:
    - `desde=0`: las últimas `limite` aprobadas, de la más vieja a la más nueva.
      Es el arranque en frío, y por eso se piden las ÚLTIMAS y no las primeras:
      una pantalla que arranca a mitad del evento tiene que mostrar lo reciente.
    - `desde=N`: las aprobadas con id > N, ascendente. Es el polling normal.

    Las dos consultas pegan contra idx_fotos_pantalla (evento_id, estado, id).

    Si las fotos del evento ya se borraron de Cloudinary (a los 30 días de su
    fecha), la lista sale vacía: las filas siguen, pero sus URLs ya no cargan.
    También desde el día del borrado aunque la pasada todavía no haya corrido o
    haya fallado a mitad: esas URLs pueden estar muertas.
    """
    if archivos_vencidos(evento):
        return ColaPantalla(fotos=[], ultimo_id=desde)

    base = select(Foto).where(Foto.evento_id == evento.id, Foto.estado == "aprobada")

    if desde == 0:
        # Las últimas `limite`: se ordena descendente para que el índice las
        # entregue directo, y se da vuelta el resultado en Python.
        filas = list(db.scalars(base.order_by(Foto.id.desc()).limit(limite)))
        filas.reverse()
    else:
        filas = list(db.scalars(base.where(Foto.id > desde).order_by(Foto.id).limit(limite)))

    fotos = [
        FotoPantalla(
            id=f.id,
            url=f.url,
            ancho=f.ancho,
            alto=f.alto,
            nombre_invitado=f.nombre_invitado,
        )
        for f in filas
    ]
    return ColaPantalla(
        fotos=fotos,
        ultimo_id=fotos[-1].id if fotos else desde,
    )


@router.post(
    "/canjear",
    response_model=TokenDePantalla,
    responses={
        404: {"model": RespuestaError, "description": "EVENTO_NO_ENCONTRADO"},
        429: {"model": RespuestaError, "description": "DEMASIADOS_PEDIDOS"},
    },
    summary="Canjear un código corto por el token de pantalla",
)
def canjear(pedido: PedidoCanje, request: Request) -> TokenDePantalla:
    """Existe para no tener que tipear 68 caracteres con el control de una tele.

    El límite de pedidos es lo que hace que un código de seis dígitos alcance:
    con 30 intentos cada 10 minutos por IP contra un millón de combinaciones, la
    probabilidad de acertar dentro de la ventana de vida del código es de 0,003%.
    Por eso la IP sale de `ip_del_pedido`, que no le cree al cliente: con la
    IP que el cliente elige, el tope no frena a nadie.
    """
    if not permitido(ip_del_pedido(request), "canje-de-pantalla"):
        raise ErrorApp(Codigo.DEMASIADOS_PEDIDOS)
    limpiar_cada_tanto()

    token = vinculacion.canjear(pedido.codigo)
    if token is None:
        # Mismo error para un código inexistente que para uno vencido o ya usado:
        # distinguirlos le diría a quien prueba al azar cuándo estuvo cerca.
        raise ErrorApp(Codigo.EVENTO_NO_ENCONTRADO, "Ese código no sirve. Generá uno nuevo")
    return TokenDePantalla(token_pantalla=token)
