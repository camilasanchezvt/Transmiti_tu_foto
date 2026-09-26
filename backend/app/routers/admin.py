"""Endpoints de administración. Base /api/admin. Todos detrás de Bearer, menos el login.

Todo lo que se consulta acá se acota por la cuenta de la sesión: un admin llega
a todos los eventos, un organizador sólo a los suyos. Un evento ajeno responde
lo mismo que uno inexistente. El backend garantiza que las fotos no se mezclen
entre eventos; lo que ninguna base previene es que se aprueben fotos del evento
equivocado con dos pestañas abiertas, y eso lo resuelve el panel.

Las cuentas (listar, habilitar, dar de baja) están en routers/cuentas.py.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from .. import vinculacion
from ..cloudinary_service import (
    ErrorVideo,
    armar_zip,
    consultar_video,
    elegir_fotos_para_video,
    nombre_del_archivo,
    pedir_video,
)
from ..database import get_db
from ..deps import es_admin, evento_del_usuario, usuario_actual
from ..errores import Codigo, ErrorApp
from ..models import Evento, Foto, Usuario
from ..ratelimit import ip_del_pedido, limpiar_cada_tanto, permitido_en_todas
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
    UsuarioYo,
    VideoEvento,
)
from ..security import (
    crear_token,
    generar_codigo_publico,
    generar_token_pantalla,
    hashear_password,
    verificar_password,
)

router = APIRouter(prefix="/api/admin", tags=["administración"])
protegido = APIRouter(
    prefix="/api/admin",
    tags=["administración"],
    dependencies=[Depends(usuario_actual)],
    responses={401: {"model": RespuestaError, "description": "NO_AUTORIZADO"}},
)

_ERROR_404_EVENTO = {404: {"model": RespuestaError, "description": "EVENTO_NO_ENCONTRADO"}}
_ERROR_404_FOTO = {404: {"model": RespuestaError, "description": "FOTO_NO_ENCONTRADA"}}
_ERROR_403 = {403: {"model": RespuestaError, "description": "NO_AUTORIZADO"}}

_SIN_PERMISO = "No tenés permiso para esto"

_PLURAL = {"pendiente": "pendientes", "aprobada": "aprobadas", "rechazada": "rechazadas"}

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# Sesión
# ─────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _hash_de_relleno() -> str:
    """Un hash cualquiera para comparar cuando el email no existe (ver login)."""
    return hashear_password("relleno-para-igualar-los-tiempos")


# Topes del login, cada 10 minutos. Cada intento cuesta un bcrypt entero (un
# cuarto de segundo de un núcleo; en Render gratuito, bastante más): sin tope,
# cualquiera prueba contraseñas sin freno o satura la única instancia durante
# un evento. Por IP frena a un script; por email frena a muchos que prueban
# contra la misma cuenta. Con un token de 12 horas, nadie de verdad llega.
MAXIMO_LOGINS_POR_IP = 10
MAXIMO_LOGINS_POR_EMAIL = 20
# No puede ser una IP ni un código público: lleva una barra.
_CLAVE_LOGIN = "admin/login"

# Un solo mensaje para "no coincide" y para "coincide pero la cuenta espera que
# la habiliten". Distinguirlos delataba qué emails existen: el registro deja
# elegir la contraseña de un email nuevo, y después el login decía "todavía no
# está habilitada" sólo si el email no existía antes.
_NO_ENTRA = "Email o contraseña incorrectos. Si recién creaste tu cuenta, esperá a que la habiliten."
_MUCHOS_INTENTOS = "Hubo muchos intentos. Esperá unos minutos y probá de nuevo."


@router.post(
    "/login",
    response_model=Sesion,
    responses={
        401: {"model": RespuestaError,
              "description": "NO_AUTORIZADO: email o contraseña incorrectos, o cuenta pendiente"},
        403: {"model": RespuestaError, "description": "NO_AUTORIZADO: cuenta dada de baja"},
        429: {"model": RespuestaError, "description": "DEMASIADOS_PEDIDOS"},
    },
    summary="Iniciar sesión",
)
def login(pedido: PedidoLogin, request: Request, db: Session = Depends(get_db)) -> Sesion:
    """Email inexistente, contraseña incorrecta y cuenta pendiente dan el mismo
    401 con el mismo mensaje, a propósito: distinguirlos permitiría averiguar
    qué direcciones están registradas. Por la misma razón, con un email
    inexistente igual se hace la comparación contra un hash de relleno: si no,
    la respuesta rápida delataría que el email no está.

    Sólo una cuenta de baja con la contraseña correcta recibe otro mensaje
    (403): esa contraseña la sabe su dueño, porque el registro nunca pisa la de
    una cuenta que ya existe. El aviso de "esperá que te habiliten" lo da la
    pantalla de Crear cuenta.

    El tope va antes de buscar la cuenta y de correr bcrypt: un pedido frenado
    no gasta nada, y frena igual exista o no el email.
    """
    email = pedido.email.strip().lower()
    if not permitido_en_todas([
        ((ip_del_pedido(request), _CLAVE_LOGIN), MAXIMO_LOGINS_POR_IP),
        ((_CLAVE_LOGIN, email), MAXIMO_LOGINS_POR_EMAIL),
    ]):
        raise ErrorApp(Codigo.DEMASIADOS_PEDIDOS, _MUCHOS_INTENTOS)
    limpiar_cada_tanto()

    usuario = db.scalar(select(Usuario).where(func.lower(Usuario.email) == email))
    if usuario is None:
        verificar_password(pedido.password, _hash_de_relleno())
        raise ErrorApp(Codigo.NO_AUTORIZADO, _NO_ENTRA)
    if not verificar_password(pedido.password, usuario.password_hash):
        raise ErrorApp(Codigo.NO_AUTORIZADO, _NO_ENTRA)
    if usuario.estado == "pendiente":
        raise ErrorApp(Codigo.NO_AUTORIZADO, _NO_ENTRA)
    if usuario.estado == "baja":
        raise ErrorApp(Codigo.NO_AUTORIZADO, "Esta cuenta está dada de baja.", http=403)
    token, expira_en = crear_token(usuario.id, usuario.email)
    return Sesion(token=token, expira_en=expira_en)


@protegido.get("/yo", response_model=UsuarioYo, summary="Quién tiene la sesión abierta")
def yo(usuario: Usuario = Depends(usuario_actual)) -> UsuarioYo:
    """El panel lo pide al entrar para saber qué mostrar: la pestaña de cuentas
    es sólo para admins y superadmins, y las acciones sobre otros admins, sólo
    para superadmins. Mostrarlas o no es comodidad; el permiso real lo exige
    cada endpoint."""
    return UsuarioYo(id=usuario.id, email=usuario.email, nombre=usuario.nombre, rol=usuario.rol)


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
    """El dueño sale de `evento.usuario`. El listado lo trae en la misma consulta
    con joinedload; en los endpoints de un solo evento es una consulta más."""
    return EventoAdmin(
        id=evento.id,
        nombre=evento.nombre,
        fecha_evento=evento.fecha_evento,
        estado=evento.estado,
        codigo_publico=evento.codigo_publico,
        token_pantalla=evento.token_pantalla,
        segundos_por_foto=evento.segundos_por_foto,
        max_fotos_por_dispositivo=evento.max_fotos_por_dispositivo,
        **totales,
        organizador_id=evento.usuario_id,
        organizador_nombre=evento.usuario.nombre,
    )


# Zona fija UTC-3 y no zoneinfo: en Windows zoneinfo no trae la base de zonas y
# rompe las pruebas, y Argentina no tiene horario de verano desde 2009.
_ARGENTINA = timezone(timedelta(hours=-3))


def hoy_en_argentina() -> date:
    """El servidor está en UTC: a las 22 h de un sábado en Buenos Aires ya es
    domingo en el servidor, y un evento de esa noche que todavía no se publicó
    pasaría al historial antes de tiempo."""
    return datetime.now(_ARGENTINA).date()


@protegido.get("/eventos", response_model=list[EventoAdmin], summary="Listar eventos")
def listar_eventos(
    alcance: Literal["vigentes", "historial"] | None = Query(
        default=None,
        description=(
            "vigentes: abiertos (de cualquier fecha) y sin publicar de hoy en adelante · "
            "historial: terminados y sin publicar de fecha pasada"
        ),
    ),
    organizador: int | None = Query(
        default=None,
        description="Sólo los eventos de esa cuenta. Sólo lo respeta un admin o un superadmin",
    ),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_actual),
) -> list[EventoAdmin]:
    """Un admin o un superadmin ve todos; un organizador, sólo los suyos, mande lo que mande.

    La regla de medianoche: un evento abierto sigue en vigentes aunque su fecha
    haya pasado, hasta que alguien lo termine. Así una fiesta que pasa la
    medianoche no se va al historial en plena pista. La fecha sólo decide para
    los que están sin publicar: de hoy en adelante son vigentes; de antes, ya
    no se van a hacer y pasan al historial. Un evento terminado va al historial
    aunque su fecha sea futura.

    Los vigentes van de lo más cercano a lo más lejano (un abierto de ayer queda
    arriba de todo, que es donde se lo busca); el historial, de lo más reciente
    a lo más viejo.
    """
    consulta = select(Evento).options(joinedload(Evento.usuario))
    if not es_admin(usuario):
        consulta = consulta.where(Evento.usuario_id == usuario.id)
    elif organizador is not None:
        consulta = consulta.where(Evento.usuario_id == organizador)

    hoy = hoy_en_argentina()
    vigente = or_(
        Evento.estado == "activo",
        and_(Evento.estado == "borrador", Evento.fecha_evento >= hoy),
    )
    del_historial = or_(
        Evento.estado == "cerrado",
        and_(Evento.estado == "borrador", Evento.fecha_evento < hoy),
    )
    if alcance == "vigentes":
        consulta = consulta.where(vigente).order_by(Evento.fecha_evento, Evento.id)
    elif alcance == "historial":
        consulta = consulta.where(del_historial).order_by(
            Evento.fecha_evento.desc(), Evento.id.desc()
        )
    else:
        consulta = consulta.order_by(Evento.fecha_evento.desc(), Evento.id.desc())

    eventos = list(db.scalars(consulta))
    totales = _contar(db, [e.id for e in eventos])
    return [_como_admin(e, totales[e.id]) for e in eventos]


def _dueno_del_evento_nuevo(nuevo: EventoNuevo, db: Session, usuario: Usuario) -> Usuario:
    """Sin `organizador_id`, o con el propio, el dueño es quien lo crea."""
    if nuevo.organizador_id is None or nuevo.organizador_id == usuario.id:
        return usuario
    if not es_admin(usuario):
        raise ErrorApp(Codigo.NO_AUTORIZADO, _SIN_PERMISO, http=403)
    dueno = db.get(Usuario, nuevo.organizador_id)
    if dueno is None or dueno.estado != "activa":
        # Mismo mensaje para una cuenta inexistente que para una pendiente o de
        # baja: en los tres casos la respuesta útil es la misma.
        raise ErrorApp(Codigo.DATOS_INVALIDOS, "Esa cuenta no está activa")
    return dueno


@protegido.post(
    "/eventos",
    response_model=EventoAdmin,
    status_code=201,
    responses={**_ERROR_403, 422: {"model": RespuestaError, "description": "DATOS_INVALIDOS"}},
    summary="Crear evento",
)
def crear_evento(
    nuevo: EventoNuevo,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_actual),
) -> EventoAdmin:
    """Nace en `borrador`, con sus dos claves generadas al azar.

    Un admin puede crearlo a nombre de otra cuenta activa con `organizador_id`.

    El UNIQUE de la base es la última palabra sobre las colisiones: si dos
    eventos se crean a la vez y sacan la misma clave, una de las dos inserciones
    falla y se reintenta con claves nuevas.
    """
    dueno = _dueno_del_evento_nuevo(nuevo, db, usuario)
    for _ in range(5):
        evento = Evento(
            usuario_id=dueno.id,
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
    summary="Cambiar el estado o la configuración de un evento",
)
def cambiar_estado_evento(
    id_evento: int,
    cambio: CambioEstadoEvento,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_actual),
) -> EventoAdmin:
    """Cerrar deja de aceptar fotos, pero la pantalla sigue pasando las aprobadas.

    Los segundos por foto le llegan a la pantalla en su próxima pasada de
    polling, sin recargarla.
    """
    evento = evento_del_usuario(id_evento, db, usuario)
    cambio_algo = False

    if cambio.estado is not None and cambio.estado != evento.estado:
        evento.estado = cambio.estado
        # Se sella cuándo se cerró; si se reabre, se borra la marca.
        evento.cerrado_en = datetime.now(timezone.utc) if cambio.estado == "cerrado" else None
        cambio_algo = True
    if cambio.segundos_por_foto is not None and cambio.segundos_por_foto != evento.segundos_por_foto:
        evento.segundos_por_foto = cambio.segundos_por_foto
        cambio_algo = True
    if (
        cambio.max_fotos_por_dispositivo is not None
        and cambio.max_fotos_por_dispositivo != evento.max_fotos_por_dispositivo
    ):
        evento.max_fotos_por_dispositivo = cambio.max_fotos_por_dispositivo
        cambio_algo = True

    if cambio_algo:
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
    usuario: Usuario = Depends(usuario_actual),
) -> Resumen:
    """Es la métrica que el panel muestra arriba y grande durante el evento."""
    evento = evento_del_usuario(id_evento, db, usuario)
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
    usuario: Usuario = Depends(usuario_actual),
) -> CodigoVinculacion:
    """Seis dígitos que la tele canjea por el token, para no tipear 68 caracteres.

    Generar uno nuevo invalida el anterior: dos códigos vivos para la misma
    pantalla es una puerta abierta de más sin ninguna ventaja.
    """
    evento = evento_del_usuario(id_evento, db, usuario)
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
    usuario: Usuario = Depends(usuario_actual),
) -> ListaFotosAdmin:
    """Ascendente por id, para que el auto-refresco de la bandeja pueda pedir
    sólo lo nuevo con `desde` sin que se le reordene lo que está mirando."""
    evento = evento_del_usuario(id_evento, db, usuario)
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


def _fotos_a_su_alcance(consulta, usuario: Usuario):
    """Un admin modera cualquier foto; un organizador, sólo las de sus eventos."""
    if es_admin(usuario):
        return consulta
    return consulta.join(Evento, Evento.id == Foto.evento_id).where(
        Evento.usuario_id == usuario.id
    )


def _foto_del_usuario(id_foto: int, db: Session, usuario: Usuario) -> Foto:
    """Una foto ajena responde lo mismo que una que no existe."""
    foto = db.scalar(_fotos_a_su_alcance(select(Foto).where(Foto.id == id_foto), usuario))
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
    usuario: Usuario = Depends(usuario_actual),
) -> FotoModerada:
    """Idempotente: si ya está en ese estado no se toca nada, ni siquiera la
    marca de cuándo se moderó. Aprobar dos veces no cambia nada la segunda vez.

    Rechazar es un estado, no un DELETE: la foto sigue existiendo y se puede
    revertir con la tecla de deshacer del panel.
    """
    foto = _foto_del_usuario(id_foto, db, usuario)
    if foto.estado != cambio.estado:
        foto.estado = cambio.estado
        foto.moderada_en = datetime.now(timezone.utc)
        foto.moderada_por = usuario.id
        db.commit()
        db.refresh(foto)
    return FotoModerada(id=foto.id, estado=foto.estado)


@protegido.post("/fotos/lote", response_model=ResultadoLote, summary="Moderar en lote")
def moderar_lote(
    lote: LoteModeracion,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_actual),
) -> ResultadoLote:
    """Un solo pedido para la ráfaga de veinte fotos casi todas buenas.

    `afectadas` cuenta las que realmente cambiaron de estado. Repetir el mismo
    lote devuelve 0: es la misma idempotencia que la moderación de a una.

    Para un organizador, las fotos de eventos ajenos se ignoran en silencio en
    vez de dar error: un id ajeno en la lista no puede impedir que se moderen
    los propios.
    """
    propias = _fotos_a_su_alcance(
        select(Foto.id).where(Foto.id.in_(lote.ids), Foto.estado != lote.estado), usuario
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
            moderada_por=usuario.id,
        )
    )
    db.commit()
    return ResultadoLote(afectadas=len(ids))


# ─────────────────────────────────────────────────────────────
# Video del evento
# ─────────────────────────────────────────────────────────────

# Si en este tiempo Cloudinary no lo terminó, se da por fallido y se puede
# volver a pedir. Sin tope, un pedido perdido dejaría el botón trabado.
_PLAZO_VIDEO = timedelta(minutes=30)


def _como_video(evento: Evento) -> VideoEvento:
    return VideoEvento(
        estado=evento.video_estado or "ninguno",
        url=evento.video_url if evento.video_estado == "listo" else None,
        fotos=evento.video_fotos,
        pedido_en=evento.video_pedido_en,
    )


@protegido.get(
    "/eventos/{id_evento}/video",
    response_model=VideoEvento,
    responses={**_ERROR_404_EVENTO},
    summary="Estado del video del evento",
)
def ver_video(
    id_evento: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_actual),
) -> VideoEvento:
    """Mientras está `procesando`, cada consulta le pregunta a Cloudinary."""
    evento = evento_del_usuario(id_evento, db, usuario)

    if evento.video_estado == "procesando" and evento.video_public_id:
        url = consultar_video(evento.video_public_id)
        if url:
            evento.video_estado = "listo"
            evento.video_url = url
            db.commit()
        elif evento.video_pedido_en and datetime.now(timezone.utc) - evento.video_pedido_en > _PLAZO_VIDEO:
            log.warning("video %s: Cloudinary no lo terminó en %s", evento.video_public_id, _PLAZO_VIDEO)
            evento.video_estado = "fallo"
            db.commit()

    return _como_video(evento)


@protegido.post(
    "/eventos/{id_evento}/video",
    response_model=VideoEvento,
    status_code=202,
    responses={**_ERROR_404_EVENTO, 422: {"model": RespuestaError, "description": "DATOS_INVALIDOS"}},
    summary="Armar el video del evento",
)
def armar_video(
    id_evento: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_actual),
) -> VideoEvento:
    """Arma un video con las fotos aprobadas, en orden de llegada.

    Si ya hay uno en proceso, no se pide otro: devuelve el que está en curso.
    Así un doble clic no gasta créditos de Cloudinary dos veces.
    """
    evento = evento_del_usuario(id_evento, db, usuario)

    en_curso = (
        evento.video_estado == "procesando"
        and evento.video_pedido_en is not None
        and datetime.now(timezone.utc) - evento.video_pedido_en <= _PLAZO_VIDEO
    )
    if en_curso:
        return _como_video(evento)

    aprobadas = list(
        db.scalars(
            select(Foto.public_id)
            .where(Foto.evento_id == evento.id, Foto.estado == "aprobada")
            .order_by(Foto.id)
        )
    )
    if not aprobadas:
        raise ErrorApp(Codigo.DATOS_INVALIDOS, "Todavía no hay fotos aprobadas para armar el video")

    elegidas = elegir_fotos_para_video(aprobadas)
    evento.video_pedido_en = datetime.now(timezone.utc)
    evento.video_fotos = len(elegidas)
    evento.video_url = None
    try:
        evento.video_public_id = pedir_video(evento.codigo_publico, elegidas)
        evento.video_estado = "procesando"
    except ErrorVideo as e:
        log.error("video del evento %s: %s", evento.id, e)
        evento.video_public_id = None
        evento.video_estado = "fallo"
    db.commit()
    return _como_video(evento)


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
    usuario: Usuario = Depends(usuario_actual),
) -> StreamingResponse:
    """El ZIP se arma y se manda al mismo tiempo, sin juntarlo en memoria.

    Con doscientas fotos de 300 KB, juntarlo entero serían 60 MB retenidos
    mientras dura la descarga, y el servicio gratuito de Render se queda sin
    memoria y se reinicia.

    Las filas se leen ANTES de empezar a mandar: la sesión de base se cierra
    cuando termina de resolverse la respuesta, y el generador sigue corriendo
    después. Si consultara adentro, lo haría sobre una sesión ya cerrada.
    """
    evento = evento_del_usuario(id_evento, db, usuario)

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
