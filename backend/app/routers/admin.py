"""Endpoints de administración. Base /api/admin. Todos detrás de Bearer.

Cada endpoint dice de qué fase es su implementación. Los que todavía no llegaron
devuelven datos fijos con la forma exacta del contrato, para que el panel se
pueda construir en paralelo.

  FASE 2 (real):  login, listado y alta de eventos
  FASE 4:         cambio de estado, fotos, resumen, moderación, lote y descarga
"""

from __future__ import annotations

import io
import zipfile
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import admin_actual
from ..errores import Codigo, ErrorApp
from ..models import Administrador, Evento, Foto
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
from ..security import (
    crear_token,
    generar_codigo_publico,
    generar_token_pantalla,
    verificar_password,
)

router = APIRouter(prefix="/api/admin", tags=["administración"])
protegido = APIRouter(
    prefix="/api/admin",
    tags=["administración"],
    dependencies=[Depends(admin_actual)],
    responses={401: {"model": RespuestaError, "description": "NO_AUTORIZADO"}},
)

_ERROR_404_EVENTO = {404: {"model": RespuestaError, "description": "EVENTO_NO_ENCONTRADO"}}


# ─────────────────────────────────────────────────────────────
# FASE 2 — sesión
# ─────────────────────────────────────────────────────────────

@router.post(
    "/login",
    response_model=Sesion,
    responses={401: {"model": RespuestaError, "description": "NO_AUTORIZADO"}},
    summary="Iniciar sesión",
)
def login(pedido: PedidoLogin, db: Session = Depends(get_db)) -> Sesion:
    """Email inexistente y contraseña incorrecta dan el mismo error a propósito:
    distinguirlos permitiría averiguar qué direcciones están registradas."""
    admin = db.scalar(
        select(Administrador).where(func.lower(Administrador.email) == pedido.email.strip().lower())
    )
    if admin is None or not verificar_password(pedido.password, admin.password_hash):
        raise ErrorApp(Codigo.NO_AUTORIZADO, "Email o contraseña incorrectos")
    token, expira_en = crear_token(admin.id, admin.email)
    return Sesion(token=token, expira_en=expira_en)


# ─────────────────────────────────────────────────────────────
# FASE 2 — eventos
# ─────────────────────────────────────────────────────────────

def _contar(db: Session, ids_evento: list[int]) -> dict[int, dict[str, int]]:
    """Totales por estado de todos los eventos en una sola consulta."""
    vacio = {"pendientes": 0, "aprobadas": 0, "rechazadas": 0}
    totales: dict[int, dict[str, int]] = {i: dict(vacio) for i in ids_evento}
    if not ids_evento:
        return totales
    filas = db.execute(
        select(Foto.evento_id, Foto.estado, func.count().label("n"))
        .where(Foto.evento_id.in_(ids_evento))
        .group_by(Foto.evento_id, Foto.estado)
    ).all()
    plural = {"pendiente": "pendientes", "aprobada": "aprobadas", "rechazada": "rechazadas"}
    for evento_id, estado, n in filas:
        totales[evento_id][plural[estado]] = n
    return totales


def _como_admin(evento: Evento, totales: dict[str, int]) -> EventoAdmin:
    return EventoAdmin(
        id=evento.id,
        nombre=evento.nombre,
        fecha_evento=evento.fecha_evento,
        estado=evento.estado,
        codigo_publico=evento.codigo_publico,
        token_pantalla=evento.token_pantalla,
        **totales,
    )


@protegido.get("/eventos", response_model=list[EventoAdmin], summary="Listar eventos")
def listar_eventos(
    db: Session = Depends(get_db), admin: Administrador = Depends(admin_actual)
) -> list[EventoAdmin]:
    eventos = list(
        db.scalars(
            select(Evento).where(Evento.admin_id == admin.id).order_by(Evento.fecha_evento.desc())
        )
    )
    totales = _contar(db, [e.id for e in eventos])
    return [_como_admin(e, totales[e.id]) for e in eventos]


@protegido.post("/eventos", response_model=EventoAdmin, status_code=201, summary="Crear evento")
def crear_evento(
    nuevo: EventoNuevo,
    db: Session = Depends(get_db),
    admin: Administrador = Depends(admin_actual),
) -> EventoAdmin:
    """Nace en `borrador`, con sus dos claves generadas al azar.

    El UNIQUE de la base es la última palabra sobre las colisiones: si dos
    eventos se crean a la vez y sacan la misma clave, una de las dos inserciones
    falla y se reintenta con claves nuevas.
    """
    for intento in range(5):
        evento = Evento(
            admin_id=admin.id,
            nombre=nuevo.nombre.strip(),
            fecha_evento=nuevo.fecha_evento,
            codigo_publico=generar_codigo_publico(),
            token_pantalla=generar_token_pantalla(),
            estado="borrador",
        )
        db.add(evento)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            continue
        db.refresh(evento)
        return _como_admin(evento, {"pendientes": 0, "aprobadas": 0, "rechazadas": 0})
    raise ErrorApp(Codigo.DATOS_INVALIDOS, "No pudimos crear el evento, probá de nuevo")


# ─────────────────────────────────────────────────────────────
# FASE 4 — todavía con datos fijos
# ─────────────────────────────────────────────────────────────

_BASE_FIJA = "https://res.cloudinary.com/demo/image/upload"

_EVENTO_FIJO = {
    "id": 1,
    "nombre": "Casamiento Ana y Juan",
    "fecha_evento": date(2026, 9, 12),
    "estado": "activo",
    "codigo_publico": "ab12cd34",
    "token_pantalla": "64syPN4YFgbJibLfIOlrjI51R0HFlKDm",
    "pendientes": 5,
    "aprobadas": 12,
    "rechazadas": 3,
}

_FOTOS_FIJAS: list[dict] = [
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


def _armar_foto_fija(fila: dict) -> FotoAdmin:
    return FotoAdmin(
        id=fila["id"],
        url=f"{_BASE_FIJA}/c_fill,w_{fila['ancho']},h_{fila['alto']}/{fila['img']}.jpg",
        ancho=fila["ancho"],
        alto=fila["alto"],
        bytes=fila["bytes"],
        estado=fila["estado"],
        nombre_invitado=fila["nombre_invitado"],
        subida_en=datetime.now(timezone.utc) - timedelta(minutes=fila["minutos"]),
    )


@protegido.patch(
    "/eventos/{id_evento}",
    response_model=EventoAdmin,
    responses={**_ERROR_404_EVENTO},
    summary="Cambiar el estado de un evento",
)
def cambiar_estado_evento(id_evento: int, cambio: CambioEstadoEvento) -> EventoAdmin:
    """FASE 4."""
    if id_evento != 1:
        raise ErrorApp(Codigo.EVENTO_NO_ENCONTRADO)
    evento = dict(_EVENTO_FIJO)
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
    """FASE 4."""
    if id_evento != 1:
        raise ErrorApp(Codigo.EVENTO_NO_ENCONTRADO)
    if estado is not None and estado not in ("pendiente", "aprobada", "rechazada"):
        raise ErrorApp(Codigo.DATOS_INVALIDOS)
    elegidas = [f for f in _FOTOS_FIJAS if estado is None or f["estado"] == estado]
    elegidas = [f for f in elegidas if f["id"] > desde][:limite]
    fotos = [_armar_foto_fija(f) for f in elegidas]
    return ListaFotosAdmin(fotos=fotos, ultimo_id=fotos[-1].id if fotos else desde)


@protegido.get(
    "/eventos/{id_evento}/resumen",
    response_model=Resumen,
    responses={**_ERROR_404_EVENTO},
    summary="Totales por estado",
)
def resumen(id_evento: int) -> Resumen:
    """FASE 4."""
    if id_evento != 1:
        raise ErrorApp(Codigo.EVENTO_NO_ENCONTRADO)
    return Resumen(pendientes=5, aprobadas=12, rechazadas=3)


@protegido.patch(
    "/fotos/{id_foto}",
    response_model=FotoModerada,
    responses={404: {"model": RespuestaError, "description": "FOTO_NO_ENCONTRADA"}},
    summary="Moderar una foto",
)
def moderar_foto(id_foto: int, cambio: CambioEstadoFoto) -> FotoModerada:
    """FASE 4. Idempotente: aprobar dos veces no cambia nada la segunda vez."""
    if id_foto <= 0:
        raise ErrorApp(Codigo.FOTO_NO_ENCONTRADA)
    return FotoModerada(id=id_foto, estado=cambio.estado)


@protegido.post("/fotos/lote", response_model=ResultadoLote, summary="Moderar en lote")
def moderar_lote(lote: LoteModeracion) -> ResultadoLote:
    """FASE 4. Una sola llamada para la ráfaga de veinte fotos casi todas buenas."""
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
    """FASE 4. El archivo se nombra con el evento y la fecha, no con un identificador."""
    if id_evento != 1:
        raise ErrorApp(Codigo.EVENTO_NO_ENCONTRADO)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(
            "LEEME.txt",
            "El ZIP con las fotos llega en la Fase 4.\n"
            f"Evento: {_EVENTO_FIJO['nombre']}\nIncluir: {incluir}\n",
        )

    nombre = f"{_EVENTO_FIJO['nombre']} - {_EVENTO_FIJO['fecha_evento'].isoformat()}.zip"
    disposicion = "attachment; filename*=UTF-8''" + quote(nombre)
    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": disposicion},
    )
