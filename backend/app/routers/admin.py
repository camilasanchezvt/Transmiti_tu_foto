"""Endpoints de administración. Base /api/admin. Todos detrás de Bearer.

Todo lo que se consulta acá se acota por el administrador de la sesión. El
backend garantiza que las fotos no se mezclen entre eventos; lo que ninguna
base previene es que el moderador apruebe fotos del evento equivocado con dos
pestañas abiertas, y eso lo resuelve el panel.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import vinculacion
from ..cloudinary_service import armar_zip, nombre_del_archivo
from ..database import get_db
from ..deps import admin_actual, evento_del_admin
from ..errores import Codigo, ErrorApp
from ..models import Administrador, Evento, Foto
from ..schemas import (
    CambioEstadoEvento,
    CambioEstadoFoto,
    CodigoVinculacion,
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
_ERROR_404_FOTO = {404: {"model": RespuestaError, "description": "FOTO_NO_ENCONTRADA"}}

_PLURAL = {"pendiente": "pendientes", "aprobada": "aprobadas", "rechazada": "rechazadas"}


# ─────────────────────────────────────────────────────────────
# Sesión
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
# Eventos
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
    for evento_id, estado, n in filas:
        totales[evento_id][_PLURAL[estado]] = n
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
    for _ in range(5):
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


@protegido.patch(
    "/eventos/{id_evento}",
    response_model=EventoAdmin,
    responses={**_ERROR_404_EVENTO},
    summary="Cambiar el estado de un evento",
)
def cambiar_estado_evento(
    id_evento: int,
    cambio: CambioEstadoEvento,
    db: Session = Depends(get_db),
    admin: Administrador = Depends(admin_actual),
) -> EventoAdmin:
    """Cerrar deja de aceptar fotos, pero la pantalla sigue pasando las aprobadas."""
    evento = evento_del_admin(id_evento, db, admin)

    if cambio.estado != evento.estado:
        evento.estado = cambio.estado
        # Se sella cuándo se cerró; si se reabre, se borra la marca.
        evento.cerrado_en = datetime.now(timezone.utc) if cambio.estado == "cerrado" else None
        db.commit()
        db.refresh(evento)

    return _como_admin(evento, _contar(db, [evento.id])[evento.id])


@protegido.get(
    "/eventos/{id_evento}/resumen",
    response_model=Resumen,
    responses={**_ERROR_404_EVENTO},
    summary="Totales por estado",
)
def resumen(
    id_evento: int,
    db: Session = Depends(get_db),
    admin: Administrador = Depends(admin_actual),
) -> Resumen:
    """Es la métrica que el panel muestra arriba y grande durante el evento."""
    evento = evento_del_admin(id_evento, db, admin)
    return Resumen(**_contar(db, [evento.id])[evento.id])


@protegido.post(
    "/eventos/{id_evento}/vincular",
    response_model=CodigoVinculacion,
    responses={**_ERROR_404_EVENTO},
    summary="Código corto para vincular una pantalla",
)
def vincular_pantalla(
    id_evento: int,
    db: Session = Depends(get_db),
    admin: Administrador = Depends(admin_actual),
) -> CodigoVinculacion:
    """Seis dígitos que la tele canjea por el token, para no tipear 68 caracteres.

    Generar uno nuevo invalida el anterior: dos códigos vivos para la misma
    pantalla es una puerta abierta de más sin ninguna ventaja.
    """
    evento = evento_del_admin(id_evento, db, admin)
    if evento.estado == "borrador":
        raise ErrorApp(Codigo.EVENTO_BORRADOR, "Publicá el evento antes de vincular la pantalla")

    codigo, segundos = vinculacion.crear(evento.id, evento.token_pantalla)
    return CodigoVinculacion(
        codigo=codigo,
        expira_en=datetime.now(timezone.utc) + timedelta(seconds=segundos),
    )


# ─────────────────────────────────────────────────────────────
# Fotos y moderación
# ─────────────────────────────────────────────────────────────

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
    db: Session = Depends(get_db),
    admin: Administrador = Depends(admin_actual),
) -> ListaFotosAdmin:
    """Ascendente por id, para que el auto-refresco de la bandeja pueda pedir
    sólo lo nuevo con `desde` sin que se le reordene lo que está mirando."""
    evento = evento_del_admin(id_evento, db, admin)
    if estado is not None and estado not in _PLURAL:
        raise ErrorApp(Codigo.DATOS_INVALIDOS, "Ese estado no existe")

    consulta = select(Foto).where(Foto.evento_id == evento.id)
    if estado is not None:
        consulta = consulta.where(Foto.estado == estado)
    if desde:
        consulta = consulta.where(Foto.id > desde)

    filas = list(db.scalars(consulta.order_by(Foto.id).limit(limite)))
    fotos = [
        FotoAdmin(
            id=f.id, url=f.url, ancho=f.ancho, alto=f.alto, bytes=f.bytes,
            estado=f.estado, nombre_invitado=f.nombre_invitado, subida_en=f.subida_en,
        )
        for f in filas
    ]
    return ListaFotosAdmin(fotos=fotos, ultimo_id=fotos[-1].id if fotos else desde)


def _foto_del_admin(id_foto: int, db: Session, admin: Administrador) -> Foto:
    """Nadie modera fotos de un evento que no es suyo."""
    foto = db.scalar(
        select(Foto).join(Evento, Evento.id == Foto.evento_id)
        .where(Foto.id == id_foto, Evento.admin_id == admin.id)
    )
    if foto is None:
        raise ErrorApp(Codigo.FOTO_NO_ENCONTRADA)
    return foto


@protegido.patch(
    "/fotos/{id_foto}",
    response_model=FotoModerada,
    responses={**_ERROR_404_FOTO},
    summary="Moderar una foto",
)
def moderar_foto(
    id_foto: int,
    cambio: CambioEstadoFoto,
    db: Session = Depends(get_db),
    admin: Administrador = Depends(admin_actual),
) -> FotoModerada:
    """Idempotente: si ya está en ese estado no se toca nada, ni siquiera la
    marca de cuándo se moderó. Aprobar dos veces no cambia nada la segunda vez.

    Rechazar es un estado, no un DELETE: la foto sigue existiendo y se puede
    revertir con la tecla de deshacer del panel.
    """
    foto = _foto_del_admin(id_foto, db, admin)
    if foto.estado != cambio.estado:
        foto.estado = cambio.estado
        foto.moderada_en = datetime.now(timezone.utc)
        foto.moderada_por = admin.id
        db.commit()
        db.refresh(foto)
    return FotoModerada(id=foto.id, estado=foto.estado)


@protegido.post("/fotos/lote", response_model=ResultadoLote, summary="Moderar en lote")
def moderar_lote(
    lote: LoteModeracion,
    db: Session = Depends(get_db),
    admin: Administrador = Depends(admin_actual),
) -> ResultadoLote:
    """Un solo pedido para la ráfaga de veinte fotos casi todas buenas.

    `afectadas` cuenta las que realmente cambiaron de estado. Repetir el mismo
    lote devuelve 0: es la misma idempotencia que la moderación de a una.

    Las fotos de otro administrador se ignoran en silencio en vez de dar error:
    un id ajeno en la lista no puede impedir que se moderen los propios.
    """
    propias = select(Foto.id).join(Evento, Evento.id == Foto.evento_id).where(
        Foto.id.in_(lote.ids), Evento.admin_id == admin.id, Foto.estado != lote.estado
    )
    ids = list(db.scalars(propias))
    if not ids:
        return ResultadoLote(afectadas=0)

    db.execute(
        update(Foto)
        .where(Foto.id.in_(ids))
        .values(
            estado=lote.estado,
            moderada_en=datetime.now(timezone.utc),
            moderada_por=admin.id,
        )
    )
    db.commit()
    return ResultadoLote(afectadas=len(ids))


# ─────────────────────────────────────────────────────────────
# Descarga
# ─────────────────────────────────────────────────────────────

@protegido.get(
    "/eventos/{id_evento}/descarga",
    responses={**_ERROR_404_EVENTO, 200: {"content": {"application/zip": {}}}},
    summary="Descargar las fotos en un ZIP",
)
def descargar(
    id_evento: int,
    incluir: str = Query(default="aprobadas", pattern="^(aprobadas|todas)$"),
    db: Session = Depends(get_db),
    admin: Administrador = Depends(admin_actual),
) -> StreamingResponse:
    """El ZIP se arma y se manda al mismo tiempo, sin juntarlo en memoria.

    Con doscientas fotos de 300 KB, juntarlo entero serían 60 MB retenidos
    mientras dura la descarga, y el servicio gratuito de Render se queda sin
    memoria y se reinicia.

    Las filas se leen ANTES de empezar a mandar: la sesión de base se cierra
    cuando termina de resolverse la respuesta, y el generador sigue corriendo
    después. Si consultara adentro, lo haría sobre una sesión ya cerrada.
    """
    evento = evento_del_admin(id_evento, db, admin)

    consulta = select(Foto.nombre_invitado, Foto.url).where(Foto.evento_id == evento.id)
    if incluir == "aprobadas":
        consulta = consulta.where(Foto.estado == "aprobada")
    # `todas` son todas, también las rechazadas. Una foto puede haberse
    # rechazado por no ser buena para proyectar y aun así los novios la quieren.

    fotos = [(nombre, url) for nombre, url in db.execute(consulta.order_by(Foto.id)).all()]

    nombre = nombre_del_archivo(evento.nombre, evento.fecha_evento)
    return StreamingResponse(
        armar_zip(fotos),
        media_type="application/zip",
        headers={
            "Content-Disposition": _disposicion(nombre),
            # Sin esto, algunos proxies bufferean el ZIP entero y se pierde el
            # sentido de armarlo en streaming.
            "X-Accel-Buffering": "no",
        },
    )


def _disposicion(nombre: str) -> str:
    from urllib.parse import quote

    return "attachment; filename*=UTF-8''" + quote(nombre)
