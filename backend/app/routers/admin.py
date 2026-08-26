"""Endpoints de administración. Base /api/admin. Todos detrás de Bearer.

FASE 1 — datos fijos. La autenticación todavía no valida nada: acepta
cualquier Bearer y sólo rechaza su ausencia, para que el panel pueda construir
el flujo de login contra esta fase. El JWT de verdad llega en la Fase 2.
"""

from __future__ import annotations

import io
import zipfile
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..errores import Codigo, ErrorApp
from ..schemas import (
    CambioEstadoEvento,
    CambioEstadoFoto,
    EventoAdmin,
    EventoNuevo,
    FotoAdmin,
    FotoModerada,
    ListaFotosAdmin,
    LoteModeracion,
    PedidoLogin,
    RespuestaError,
    Resumen,
    ResultadoLote,
    Sesion,
)

_esquema_bearer = HTTPBearer(auto_error=False)


def admin_actual(
    credenciales: HTTPAuthorizationCredentials | None = Depends(_esquema_bearer),
) -> str:
    """FASE 1: sólo exige que venga el Bearer. La Fase 2 valida el JWT de verdad."""
    if credenciales is None or not credenciales.credentials:
        raise ErrorApp(Codigo.NO_AUTORIZADO)
    return "ana@transmitifoto.test"


router = APIRouter(prefix="/api/admin", tags=["administración"])
protegido = APIRouter(
    prefix="/api/admin",
    tags=["administración"],
    dependencies=[Depends(admin_actual)],
    responses={401: {"model": RespuestaError, "description": "NO_AUTORIZADO"}},
)

_BASE = "https://res.cloudinary.com/demo/image/upload"

_EVENTOS: dict[int, dict] = {
    1: {
        "id": 1,
        "nombre": "Casamiento Ana y Juan",
        "fecha_evento": date(2026, 9, 12),
        "estado": "activo",
        "codigo_publico": "ab12cd34",
        "token_pantalla": "64syPN4YFgbJibLfIOlrjI51R0HFlKDm",
        "pendientes": 5,
        "aprobadas": 12,
        "rechazadas": 3,
    },
    2: {
        "id": 2,
        "nombre": "Cumple de 15 de Malena",
        "fecha_evento": date(2026, 7, 4),
        "estado": "cerrado",
        "codigo_publico": "ef56gh78",
        "token_pantalla": "8MX4OqECds7IhkCmlK7vub76PntouGz1",
        "pendientes": 1,
        "aprobadas": 3,
        "rechazadas": 0,
    },
}

# Las cinco pendientes del evento 1: es lo que ve la bandeja de moderación.
_FOTOS: list[dict] = [
    {"id": 121, "img": "bike", "ancho": 1600, "alto": 1200, "bytes": 254442,
     "estado": "pendiente", "nombre_invitado": "", "minutos": 82},
    {"id": 124, "img": "cld-sample-3", "ancho": 1600, "alto": 1200, "bytes": 246604,
     "estado": "pendiente", "nombre_invitado": "Agustín Iñíguez", "minutos": 40},
    {"id": 127, "img": "cld-sample-4", "ancho": 1200, "alto": 1600, "bytes": 249215,
     "estado": "pendiente", "nombre_invitado": "Malén Ibáñez", "minutos": 22},
    {"id": 129, "img": "cld-sample-5", "ancho": 1600, "alto": 600, "bytes": 78466,
     "estado": "pendiente", "nombre_invitado": None, "minutos": 10},
    {"id": 130, "img": "cld-sample", "ancho": 1200, "alto": 1600, "bytes": 225467,
     "estado": "pendiente", "nombre_invitado": "Martín Peña", "minutos": 4},
]

_ERROR_404_EVENTO = {404: {"model": RespuestaError, "description": "EVENTO_NO_ENCONTRADO"}}


def _buscar_evento(id_evento: int) -> dict:
    evento = _EVENTOS.get(id_evento)
    if evento is None:
        raise ErrorApp(Codigo.EVENTO_NO_ENCONTRADO)
    return evento


def _armar_foto(fila: dict) -> FotoAdmin:
    return FotoAdmin(
        id=fila["id"],
        url=f"{_BASE}/c_fill,w_{fila['ancho']},h_{fila['alto']}/{fila['img']}.jpg",
        ancho=fila["ancho"],
        alto=fila["alto"],
        bytes=fila["bytes"],
        estado=fila["estado"],
        nombre_invitado=fila["nombre_invitado"],
        subida_en=datetime.now(timezone.utc) - timedelta(minutes=fila["minutos"]),
    )


@router.post(
    "/login",
    response_model=Sesion,
    responses={401: {"model": RespuestaError, "description": "NO_AUTORIZADO"}},
    summary="Iniciar sesión",
)
def login(pedido: PedidoLogin) -> Sesion:
    """FASE 1: acepta cualquier email con contraseña no vacía."""
    if not pedido.email or not pedido.password:
        raise ErrorApp(Codigo.NO_AUTORIZADO)
    return Sesion(
        token="fase1-token-de-prueba",
        expira_en=datetime.now(timezone.utc) + timedelta(hours=12),
    )


@protegido.get("/eventos", response_model=list[EventoAdmin], summary="Listar eventos")
def listar_eventos() -> list[EventoAdmin]:
    return [EventoAdmin(**e) for e in _EVENTOS.values()]


@protegido.post("/eventos", response_model=EventoAdmin, status_code=201, summary="Crear evento")
def crear_evento(nuevo: EventoNuevo) -> EventoAdmin:
    """Nace en `borrador`, con sus dos claves ya generadas."""
    return EventoAdmin(
        id=3,
        nombre=nuevo.nombre,
        fecha_evento=nuevo.fecha_evento,
        estado="borrador",
        codigo_publico="qr90st12",
        token_pantalla="Xk7pQ2mR9vL4nT6wY8zB3cF5hJ1dG0sA",
        pendientes=0,
        aprobadas=0,
        rechazadas=0,
    )


@protegido.patch(
    "/eventos/{id_evento}",
    response_model=EventoAdmin,
    responses={**_ERROR_404_EVENTO},
    summary="Cambiar el estado de un evento",
)
def cambiar_estado_evento(id_evento: int, cambio: CambioEstadoEvento) -> EventoAdmin:
    evento = dict(_buscar_evento(id_evento))
    evento["estado"] = cambio.estado
    return EventoAdmin(**evento)


@protegido.get(
    "/eventos/{id_evento}/fotos",
    response_model=ListaFotosAdmin,
    responses={**_ERROR_404_EVENTO},
    summary="Fotos de un evento",
)
def listar_fotos(
    id_evento: int,
    estado: str | None = Query(default=None, description="pendiente · aprobada · rechazada"),
    desde: int = Query(default=0, ge=0),
    limite: int = Query(default=40, ge=1, le=200),
) -> ListaFotosAdmin:
    _buscar_evento(id_evento)
    if estado is not None and estado not in ("pendiente", "aprobada", "rechazada"):
        raise ErrorApp(Codigo.DATOS_INVALIDOS)
    elegidas = [f for f in _FOTOS if estado is None or f["estado"] == estado]
    elegidas = [f for f in elegidas if f["id"] > desde][:limite]
    fotos = [_armar_foto(f) for f in elegidas]
    return ListaFotosAdmin(fotos=fotos, ultimo_id=fotos[-1].id if fotos else desde)


@protegido.get(
    "/eventos/{id_evento}/resumen",
    response_model=Resumen,
    responses={**_ERROR_404_EVENTO},
    summary="Totales por estado",
)
def resumen(id_evento: int) -> Resumen:
    evento = _buscar_evento(id_evento)
    return Resumen(
        pendientes=evento["pendientes"],
        aprobadas=evento["aprobadas"],
        rechazadas=evento["rechazadas"],
    )


@protegido.patch(
    "/fotos/{id_foto}",
    response_model=FotoModerada,
    responses={404: {"model": RespuestaError, "description": "FOTO_NO_ENCONTRADA"}},
    summary="Moderar una foto",
)
def moderar_foto(id_foto: int, cambio: CambioEstadoFoto) -> FotoModerada:
    """Idempotente: aprobar dos veces la misma foto no cambia nada la segunda vez."""
    if id_foto <= 0:
        raise ErrorApp(Codigo.FOTO_NO_ENCONTRADA)
    return FotoModerada(id=id_foto, estado=cambio.estado)


@protegido.post("/fotos/lote", response_model=ResultadoLote, summary="Moderar en lote")
def moderar_lote(lote: LoteModeracion) -> ResultadoLote:
    """Una sola llamada para la ráfaga de veinte fotos casi todas buenas."""
    return ResultadoLote(afectadas=len(lote.ids))


@protegido.get(
    "/eventos/{id_evento}/descarga",
    responses={**_ERROR_404_EVENTO, 200: {"content": {"application/zip": {}}}},
    summary="Descargar las fotos en un ZIP",
)
def descargar(
    id_evento: int,
    incluir: str = Query(default="aprobadas", pattern="^(aprobadas|todas)$"),
) -> Response:
    """El archivo se nombra con el evento y la fecha, no con un identificador."""
    evento = _buscar_evento(id_evento)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(
            "LEEME.txt",
            "Fase 1: el ZIP todavía no trae fotos.\n"
            f"Evento: {evento['nombre']}\nIncluir: {incluir}\n",
        )

    nombre = f"{evento['nombre']} - {evento['fecha_evento'].isoformat()}.zip"
    disposicion = "attachment; filename*=UTF-8''" + quote(nombre)
    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": disposicion},
    )
