"""Endpoints de administración. Base /api/admin. Todos detrás de Bearer, menos el login.

Todo lo que se consulta acá se acota por la cuenta de la sesión: un admin llega
a todos los eventos, un organizador sólo a los suyos. Un evento ajeno responde
lo mismo que uno inexistente. El backend garantiza que las fotos no se mezclen
entre eventos; lo que ninguna base previene es que se aprueben fotos del evento
equivocado con dos pestañas abiertas, y eso lo resuelve el panel.

Las cuentas (listar, habilitar, dar de baja) están en routers/cuentas.py.

Borrar un evento del Historial (`borrar_evento`, sólo admin y superadmin) es la
segunda excepción a "nada se borra", junto con eliminar una cuenta: se va el
evento con sus fotos, de la base y de Cloudinary.

Mi cuenta (`/yo`) también vive acá: cada cuenta cambia su nombre, su tema, sus
predeterminados, su contraseña y su avatar. Nunca su email, su rol ni su
estado. "Olvidé mi contraseña", que es sin sesión, está en routers/cuentas.py.
"""

from __future__ import annotations

import logging
import unicodedata
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import ColumnElement, and_, delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.orm.exc import StaleDataError

from .. import vinculacion
from ..cloudinary_service import (
    ErrorBorrado,
    ErrorVideo,
    armar_zip,
    borrar_archivos_del_evento,
    borrar_avatar_anterior,
    carpeta_de_avatares,
    consultar_video,
    elegir_fotos_para_video,
    firmar_carpeta,
    nombre_del_archivo,
    pedir_video,
    verificar_avatar,
    verificar_url,
)
from ..database import get_db
from ..deps import es_admin, evento_del_usuario, solo_admin, usuario_actual
from ..errores import Codigo, ErrorApp
from ..fechas import hoy_en_argentina
from ..limpieza import archivos_vencidos, fecha_vencida, fotos_se_borran_el
from ..models import Evento, Foto, Usuario
from ..ratelimit import ip_del_pedido, limpiar_cada_tanto, permitido, permitido_en_todas
from ..schemas import (
    AvatarNuevo,
    CambioEstadoEvento,
    CambioEstadoFoto,
    CambioYo,
    CodigoVinculacion,
    EstiloPantalla,
    EventoAdmin,
    EventoBorrado,
    EventoNuevo,
    Firma,
    FotoAdmin,
    FotoModerada,
    ListaFotosAdmin,
    LoteModeracion,
    PedidoBorrarEvento,
    PedidoCambioContrasena,
    PedidoLogin,
    Predeterminados,
    RespuestaError,
    Resumen,
    ResultadoLote,
    Sesion,
    UsuarioYo,
    VideoEvento,
)
from ..security import (
    al_milisegundo,
    crear_token,
    generar_codigo_publico,
    generar_token_pantalla,
    hashear_password,
    verificar_password,
)
from .cuentas import anular_recuperaciones

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
_ERROR_410 = {410: {"model": RespuestaError,
                    "description": "DATOS_INVALIDOS: las fotos y el video ya se borraron"}}

_SIN_PERMISO = "No tenés permiso para esto"

_PLURAL = {"pendiente": "pendientes", "aprobada": "aprobadas", "rechazada": "rechazadas"}

log = logging.getLogger(__name__)

# Hijo del de uvicorn, que en Render sale en el log a nivel INFO (el de
# `app.*` sólo mostraría los errores). Los mensajes empiezan con "eventos:"
# porque el log de uvicorn no muestra el nombre del logger.
log_eventos = logging.getLogger("uvicorn.error").getChild("eventos")


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

    La fila de la cuenta se lee con FOR SHARE, y el lock dura hasta que
    `get_db` cierra la sesión, o sea, hasta DESPUÉS de emitir el token. Sin
    él, un login con la contraseña vieja que leía el hash mientras alguien
    restablecía la contraseña (todavía sin confirmar) corría bcrypt, emitía
    el token con un `iat` posterior al `sesiones_desde` nuevo y quedaba adentro
    doce horas, justo lo que restablecer tenía que cortar. FOR SHARE choca con
    el FOR NO KEY UPDATE de restablecer y de cambiar la contraseña, así que
    quedan dos casos: si el cambio va primero, el login espera, relee la fila
    y ve el hash nuevo (401); si el login va primero, el cambio espera a que
    termine y su `sesiones_desde` queda después del `iat`, así que el token
    muere. Dos logins a la vez no se frenan entre sí, y las FK de fotos y
    eventos (FOR KEY SHARE) tampoco chocan: lo único que espera, lo que dura
    un bcrypt, es un cambio a esta misma cuenta.
    """
    email = pedido.email.strip().lower()
    if not permitido_en_todas([
        ((ip_del_pedido(request), _CLAVE_LOGIN), MAXIMO_LOGINS_POR_IP),
        ((_CLAVE_LOGIN, email), MAXIMO_LOGINS_POR_EMAIL),
    ]):
        raise ErrorApp(Codigo.DEMASIADOS_PEDIDOS, _MUCHOS_INTENTOS)
    limpiar_cada_tanto()

    usuario = db.scalar(
        select(Usuario)
        .where(func.lower(Usuario.email) == email)
        .with_for_update(read=True)
    )
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


# ─────────────────────────────────────────────────────────────
# Mi cuenta
# ─────────────────────────────────────────────────────────────

def _como_yo(usuario: Usuario) -> UsuarioYo:
    return UsuarioYo(
        id=usuario.id,
        email=usuario.email,
        nombre=usuario.nombre,
        rol=usuario.rol,
        avatar_url=usuario.avatar_url,
        tema=usuario.tema,
        predeterminados=Predeterminados(
            segundos_por_foto=usuario.pred_segundos_por_foto,
            max_fotos_por_dispositivo=usuario.pred_max_fotos_por_dispositivo,
            pantalla=EstiloPantalla(
                fondo=usuario.pred_pantalla_fondo,
                transicion=usuario.pred_pantalla_transicion,
                mostrar_nombre=usuario.pred_pantalla_nombre,
                mostrar_qr=usuario.pred_pantalla_qr,
            ),
        ),
    )


@protegido.get("/yo", response_model=UsuarioYo, summary="Quién tiene la sesión abierta")
def yo(usuario: Usuario = Depends(usuario_actual)) -> UsuarioYo:
    """El panel lo pide al entrar para saber qué mostrar: la pestaña de cuentas
    es sólo para admins y superadmins, y las acciones sobre otros admins, sólo
    para superadmins. Mostrarlas o no es comodidad; el permiso real lo exige
    cada endpoint.

    Trae también lo de Mi cuenta: el avatar, el tema del panel (el panel lo
    aplica al entrar) y los predeterminados de los eventos nuevos."""
    return _como_yo(usuario)


# De CambioYo.valores() a la columna de `usuarios`.
_COLUMNA_DE = {
    "nombre": "nombre",
    "tema": "tema",
    "segundos_por_foto": "pred_segundos_por_foto",
    "max_fotos_por_dispositivo": "pred_max_fotos_por_dispositivo",
    "pantalla.fondo": "pred_pantalla_fondo",
    "pantalla.transicion": "pred_pantalla_transicion",
    "pantalla.mostrar_nombre": "pred_pantalla_nombre",
    "pantalla.mostrar_qr": "pred_pantalla_qr",
}


@protegido.patch(
    "/yo",
    response_model=UsuarioYo,
    responses={422: {"model": RespuestaError,
                     "description": "DATOS_INVALIDOS (también un campo que no existe, "
                                    "como email, rol o estado)"}},
    summary="Cambiar mi nombre, mi tema o mis predeterminados",
)
def cambiar_yo(
    cambio: CambioYo,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_actual),
) -> UsuarioYo:
    """Todo parcial: lo que no viene no se toca, y hace falta al menos un valor.

    Los predeterminados se copian a los eventos que se creen DESPUÉS; los que
    ya existen no cambian. El email, el rol y el estado no se cambian acá (ni
    son campos de este cuerpo: mandarlos es 422).

    Idempotente: si no cambia nada, no se toca nada.
    """
    cambio_algo = False
    for clave, valor in cambio.valores().items():
        columna = _COLUMNA_DE[clave]
        if getattr(usuario, columna) != valor:
            setattr(usuario, columna, valor)
            cambio_algo = True
    if cambio_algo:
        db.commit()
        db.refresh(usuario)
    return _como_yo(usuario)


# Cambiar la contraseña con la actual: sin tope, una sesión robada (o una
# compu que quedó abierta) serviría para probar contraseñas contra la cuenta
# hasta dar con la actual, y después cambiarla y dejar afuera a su dueña. Cinco
# por hora y por cuenta alcanzan para equivocarse al tipear.
MAXIMO_CAMBIOS_DE_CONTRASENA = 5
VENTANA_CAMBIOS_DE_CONTRASENA = 3600
_CLAVE_CONTRASENA = "admin/contrasena"
_ACTUAL_INCORRECTA = "La contraseña actual no es correcta"
_MUCHOS_CAMBIOS = "Hubo muchos intentos. Esperá un rato y probá de nuevo."


@protegido.post(
    "/yo/contrasena",
    response_model=Sesion,
    responses={
        422: {"model": RespuestaError,
              "description": "DATOS_INVALIDOS: la contraseña actual no es correcta, o la "
                             "nueva no tiene entre 10 y 128 caracteres"},
        429: {"model": RespuestaError, "description": "DEMASIADOS_PEDIDOS"},
    },
    summary="Cambiar mi contraseña",
)
def cambiar_contrasena(
    pedido: PedidoCambioContrasena,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_actual),
) -> Sesion:
    """Pide la contraseña actual aunque la sesión sea válida: una sesión abierta
    en una compu ajena no alcanza para quedarse con la cuenta.

    Cierra TODAS las sesiones abiertas de la cuenta (`sesiones_desde`) y
    devuelve una sesión nueva, emitida en ese mismo instante, para que quien
    la cambió siga adentro: el panel guarda el token nuevo. También anula los
    links de "olvidé mi contraseña" que seguían vivos.

    El tope va antes de bcrypt, como en el login: un pedido frenado no gasta nada.

    La fila de la cuenta se relee con FOR NO KEY UPDATE antes de comparar la
    contraseña. `usuario_actual` la leyó sin lock, y si la dueña canjea el link
    del email mientras tanto, comparar contra ese hash viejo dejaría que una
    sesión robada pisara la contraseña que ella acaba de elegir. Con el lock,
    o se espera a que el canje confirme, o el canje espera a este pedido. Así
    el orden de locks es el mismo que en /recuperar: primero la cuenta, después
    sus pedidos de recuperación.
    """
    if not permitido(
        _CLAVE_CONTRASENA, str(usuario.id),
        maximo=MAXIMO_CAMBIOS_DE_CONTRASENA, ventana=VENTANA_CAMBIOS_DE_CONTRASENA,
    ):
        raise ErrorApp(Codigo.DEMASIADOS_PEDIDOS, _MUCHOS_CAMBIOS)
    limpiar_cada_tanto()

    # `refresh` pisa los atributos del mismo objeto: lo leído por
    # `usuario_actual` se guarda antes para ver si cambió en el medio.
    sesiones_desde_validado = usuario.sesiones_desde
    db.refresh(usuario, with_for_update={"key_share": True})
    if usuario.estado != "activa":
        raise ErrorApp(Codigo.NO_AUTORIZADO)
    # Si alguien cerró las sesiones mientras este pedido estaba en vuelo (un
    # restablecimiento u otro cambio de contraseña), la sesión que lo trajo ya
    # no vale: mismo 401 que daría `usuario_actual` en el pedido siguiente.
    if usuario.sesiones_desde != sesiones_desde_validado:
        raise ErrorApp(Codigo.NO_AUTORIZADO)

    if not verificar_password(pedido.actual, usuario.password_hash):
        raise ErrorApp(Codigo.DATOS_INVALIDOS, _ACTUAL_INCORRECTA)

    usuario.password_hash = hashear_password(pedido.nueva)
    momento = al_milisegundo(datetime.now(timezone.utc))
    usuario.sesiones_desde = momento
    anular_recuperaciones(db, usuario.id, momento)
    db.commit()
    log.info("cuentas: la cuenta %s cambió su contraseña desde Mi cuenta", usuario.id)
    token, expira_en = crear_token(usuario.id, usuario.email, emitido_en=momento)
    return Sesion(token=token, expira_en=expira_en)


# Firmas de avatar por cuenta y por hora. Cada firma deja subir imágenes a
# Cloudinary durante una hora; sin tope, una sesión podría llenar el cupo.
MAXIMO_FIRMAS_DE_AVATAR = 20
VENTANA_FIRMAS_DE_AVATAR = 3600
_CLAVE_FIRMA_AVATAR = "admin/avatar"


@protegido.post(
    "/yo/avatar/firma",
    response_model=Firma,
    responses={429: {"model": RespuestaError, "description": "DEMASIADOS_PEDIDOS"}},
    summary="Firma para subir mi avatar a Cloudinary",
)
def firmar_avatar(usuario: Usuario = Depends(usuario_actual)) -> Firma:
    """La misma firma que la de las fotos (sólo `folder` y `timestamp`), para la
    carpeta `avatares/{id}` de la cuenta. El navegador sube directo a
    Cloudinary y después guarda el resultado con PUT /api/admin/yo/avatar."""
    if not permitido(
        _CLAVE_FIRMA_AVATAR, str(usuario.id),
        maximo=MAXIMO_FIRMAS_DE_AVATAR, ventana=VENTANA_FIRMAS_DE_AVATAR,
    ):
        raise ErrorApp(Codigo.DEMASIADOS_PEDIDOS)
    limpiar_cada_tanto()
    return Firma(**firmar_carpeta(carpeta_de_avatares(usuario.id)))


@protegido.put(
    "/yo/avatar",
    response_model=UsuarioYo,
    responses={
        400: {"model": RespuestaError, "description": "ARCHIVO_INVALIDO"},
        403: {"model": RespuestaError, "description": "PUBLIC_ID_AJENO"},
    },
    summary="Guardar mi avatar ya subido a Cloudinary",
)
def guardar_avatar(
    avatar: AvatarNuevo,
    tareas: BackgroundTasks,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_actual),
) -> UsuarioYo:
    """Las mismas verificaciones que una foto de invitado (regla 4): el
    `public_id` tiene que estar en `avatares/{id}/` de esta cuenta, sin
    subcarpetas (si no, PUBLIC_ID_AJENO), y la `url` tiene que ser exactamente
    la de esa imagen en la cuenta de Cloudinary de la app (si no,
    ARCHIVO_INVALIDO). Sin esto, una cuenta podría mostrar de avatar cualquier
    imagen de internet, o una foto de un evento.

    Si reemplaza a otro, el anterior se borra de Cloudinary en segundo plano y
    a mejor esfuerzo. Guardar el mismo otra vez no cambia nada.
    """
    verificar_avatar(avatar.public_id, usuario.id)
    verificar_url(avatar.url, avatar.public_id)

    anterior = usuario.avatar_public_id
    if anterior != avatar.public_id or usuario.avatar_url != avatar.url:
        usuario.avatar_public_id = avatar.public_id
        usuario.avatar_url = avatar.url
        db.commit()
        db.refresh(usuario)
        if anterior is not None and anterior != avatar.public_id:
            tareas.add_task(borrar_avatar_anterior, anterior, usuario.id)
    return _como_yo(usuario)


@protegido.post(
    "/yo/avatar/quitar",
    response_model=UsuarioYo,
    summary="Quitar mi avatar",
)
def quitar_avatar(
    tareas: BackgroundTasks,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_actual),
) -> UsuarioYo:
    """Deja el avatar en null; el panel vuelve a mostrar la inicial. La imagen
    se borra de Cloudinary en segundo plano y a mejor esfuerzo. Idempotente:
    sin avatar, no hace nada."""
    anterior = usuario.avatar_public_id
    if anterior is not None or usuario.avatar_url is not None:
        usuario.avatar_public_id = None
        usuario.avatar_url = None
        db.commit()
        db.refresh(usuario)
        if anterior is not None:
            tareas.add_task(borrar_avatar_anterior, anterior, usuario.id)
    return _como_yo(usuario)


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
    con joinedload; en los endpoints de un solo evento es una consulta más.

    `video_url_listo` sale de la misma fila: el panel puede ofrecer descargar
    el video desde la lista sin preguntarle nada a Cloudinary. Desde el día del
    borrado es null aunque la pasada todavía no haya corrido (mismo criterio
    que `_exigir_archivos`): el link llevaría a un video que se está borrando."""
    vencidos = archivos_vencidos(evento)
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
        fotos_se_borran_el=fotos_se_borran_el(evento.fecha_evento),
        fotos_borradas_en=evento.fotos_borradas_en,
        video_url_listo=(
            evento.video_url if evento.video_estado == "listo" and not vencidos else None
        ),
        pantalla_fondo=evento.pantalla_fondo,
        pantalla_transicion=evento.pantalla_transicion,
        pantalla_mostrar_nombre=evento.pantalla_mostrar_nombre,
        pantalla_mostrar_qr=evento.pantalla_mostrar_qr,
    )


# Las fotos y el video de un evento se borran de Cloudinary a los 30 días de su
# fecha (app/limpieza.py). Desde ese día, lo que necesita los archivos responde
# 410, se hayan borrado ya o todavía no.
_YA_SE_BORRARON = "Las fotos y el video de este evento ya se borraron"
_SE_ESTAN_BORRANDO = "Las fotos y el video de este evento se están borrando"


def _exigir_archivos(evento: Evento) -> None:
    """410 y no 404: el evento existe, lo que ya no existe son sus archivos.

    El corte es la FECHA del borrado, no sólo `fotos_borradas_en`: ese día la
    pasada puede correr en cualquier momento (en Render gratuito, un minuto
    después de que la organizadora despierta la API entrando a descargar), y
    una descarga en curso quedaba a medias sin que nadie se enterara."""
    if evento.fotos_borradas_en is not None:
        raise ErrorApp(Codigo.DATOS_INVALIDOS, _YA_SE_BORRARON, http=410)
    if fecha_vencida(evento.fecha_evento):
        raise ErrorApp(Codigo.DATOS_INVALIDOS, _SE_ESTAN_BORRANDO, http=410)


def del_vigente(hoy: date) -> ColumnElement[bool]:
    """`alcance=vigentes`: abiertos de cualquier fecha y sin publicar de hoy en adelante."""
    return or_(
        Evento.estado == "activo",
        and_(Evento.estado == "borrador", Evento.fecha_evento >= hoy),
    )


def del_historial(hoy: date) -> ColumnElement[bool]:
    """`alcance=historial`: terminados de cualquier fecha y sin publicar de fecha
    pasada. Es EL criterio del Historial: lo usan el listado y `borrar_evento`,
    que sólo borra lo que el listado muestra ahí."""
    return or_(
        Evento.estado == "cerrado",
        and_(Evento.estado == "borrador", Evento.fecha_evento < hoy),
    )


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
    if alcance == "vigentes":
        consulta = consulta.where(del_vigente(hoy)).order_by(Evento.fecha_evento, Evento.id)
    elif alcance == "historial":
        consulta = consulta.where(del_historial(hoy)).order_by(
            Evento.fecha_evento.desc(), Evento.id.desc()
        )
    else:
        consulta = consulta.order_by(Evento.fecha_evento.desc(), Evento.id.desc())

    eventos = list(db.scalars(consulta))
    totales = _contar(db, [e.id for e in eventos])
    return [_como_admin(e, totales[e.id]) for e in eventos]


# Lo lee quien organiza, en el formulario de Crear evento (ver crear_evento).
_FECHA_VENCIDA = "Esa fecha ya pasó hace 30 días o más. Revisá el año"


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
    responses={
        **_ERROR_403,
        422: {"model": RespuestaError,
              "description": "DATOS_INVALIDOS (también una fecha de hace 30 días o más)"},
    },
    summary="Crear evento",
)
def crear_evento(
    nuevo: EventoNuevo,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_actual),
) -> EventoAdmin:
    """Nace en `borrador`, con sus dos claves generadas al azar.

    Un admin puede crearlo a nombre de otra cuenta activa con `organizador_id`.

    Nace con los predeterminados del DUEÑO (Mi cuenta): segundos por foto,
    fotos por invitado y el estilo de la pantalla. Si un admin lo crea para
    otra cuenta, son los de esa cuenta y no los del admin: el evento es de ella.

    Una fecha de hace 30 días o más se rechaza: sus archivos ya estarían
    vencidos, y la próxima pasada de limpieza lo cerraría y lo borraría sin
    dejar reabrirlo (la fecha no se puede cambiar después). Casi siempre es el
    año mal puesto. Una fecha de hace menos sí vale: sirve para juntar las
    fotos de una fiesta que ya pasó.

    El UNIQUE de la base es la última palabra sobre las colisiones: si dos
    eventos se crean a la vez y sacan la misma clave, una de las dos inserciones
    falla y se reintenta con claves nuevas.
    """
    if fecha_vencida(nuevo.fecha_evento):
        raise ErrorApp(Codigo.DATOS_INVALIDOS, _FECHA_VENCIDA)
    dueno = _dueno_del_evento_nuevo(nuevo, db, usuario)
    for _ in range(5):
        evento = Evento(
            usuario_id=dueno.id,
            nombre=nuevo.nombre,  # ya viene recortado (NombreEvento)
            fecha_evento=nuevo.fecha_evento,
            codigo_publico=generar_codigo_publico(),
            token_pantalla=generar_token_pantalla(),
            estado="borrador",
            segundos_por_foto=dueno.pred_segundos_por_foto,
            max_fotos_por_dispositivo=dueno.pred_max_fotos_por_dispositivo,
            pantalla_fondo=dueno.pred_pantalla_fondo,
            pantalla_transicion=dueno.pred_pantalla_transicion,
            pantalla_mostrar_nombre=dueno.pred_pantalla_nombre,
            pantalla_mostrar_qr=dueno.pred_pantalla_qr,
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
    responses={
        **_ERROR_404_EVENTO,
        409: {"model": RespuestaError,
              "description": "DATOS_INVALIDOS: no se reabre un evento con las fotos borradas "
                             "o que se están borrando"},
    },
    summary="Cambiar el estado o la configuración de un evento",
)
def cambiar_estado_evento(
    id_evento: int,
    cambio: CambioEstadoEvento,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_actual),
) -> EventoAdmin:
    """Cerrar deja de aceptar fotos, pero la pantalla sigue pasando las aprobadas.

    Los segundos por foto y el estilo de la pantalla (`pantalla_*`) le llegan
    a la pantalla en su próxima pasada de polling, sin recargarla.

    Un evento con las fotos ya borradas de Cloudinary no se reabre (409): los
    invitados subirían fotos a una carpeta que ya se limpió y que nadie va a
    volver a limpiar, y la pantalla no tendría nada que mostrar. Tampoco desde
    el día del borrado, aunque la pasada todavía no haya corrido: la pasada lo
    cerraría enseguida y borraría lo que llegara.
    """
    evento = evento_del_usuario(id_evento, db, usuario)
    cambio_algo = False

    if cambio.estado is not None and cambio.estado != evento.estado:
        if archivos_vencidos(evento) and cambio.estado != "cerrado":
            raise ErrorApp(
                Codigo.DATOS_INVALIDOS,
                "Las fotos de este evento ya se borraron: no se puede reabrir"
                if evento.fotos_borradas_en is not None
                else "Las fotos de este evento se están borrando: no se puede reabrir",
                http=409,
            )
        evento.estado = cambio.estado
        # Se sella cuándo se cerró; si se reabre, se borra la marca.
        evento.cerrado_en = datetime.now(timezone.utc) if cambio.estado == "cerrado" else None
        cambio_algo = True
    if cambio.segundos_por_foto is not None and cambio.segundos_por_foto != evento.segundos_por_foto:
        evento.segundos_por_foto = cambio.segundos_por_foto
        cambio_algo = True
    for campo in (
        "max_fotos_por_dispositivo",
        "pantalla_fondo",
        "pantalla_transicion",
        "pantalla_mostrar_nombre",
        "pantalla_mostrar_qr",
    ):
        valor = getattr(cambio, campo)
        if valor is not None and valor != getattr(evento, campo):
            setattr(evento, campo, valor)
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


def _video_en_curso(evento: Evento) -> bool:
    """Cloudinary lo está armando: se pidió hace menos de `_PLAZO_VIDEO` y nadie
    vio todavía que esté listo. Lo usan armar_video (no pedir otro) y
    borrar_evento (no borrar la carpeta con un video por aparecer)."""
    return (
        evento.video_estado == "procesando"
        and evento.video_pedido_en is not None
        and datetime.now(timezone.utc) - evento.video_pedido_en <= _PLAZO_VIDEO
    )


def _tomar_evento_del_usuario(id_evento: int, db: Session, usuario: Usuario) -> Evento:
    """Como `evento_del_usuario` (mismo 404 para uno ajeno o inexistente), pero
    con la fila tomada con FOR NO KEY UPDATE hasta el commit.

    Choca con el FOR UPDATE de borrar_evento y con otro pedido igual, y no con
    el alta de una foto (FOR KEY SHARE, por la clave foránea): los invitados
    siguen subiendo mientras tanto."""
    evento = db.get(Evento, id_evento, with_for_update={"key_share": True})
    if evento is None or not (es_admin(usuario) or evento.usuario_id == usuario.id):
        raise ErrorApp(Codigo.EVENTO_NO_ENCONTRADO)
    return evento


def _guardar_o_404(db: Session) -> None:
    """Commit de un cambio sobre la fila del evento leída sin lock. Si en el
    medio se borró el evento (DELETE del Historial), el UPDATE no encuentra la
    fila: 404, como cualquier evento que no existe, y no un 500."""
    try:
        db.commit()
    except StaleDataError:
        db.rollback()
        raise ErrorApp(Codigo.EVENTO_NO_ENCONTRADO) from None


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
    responses={**_ERROR_404_EVENTO, **_ERROR_410},
    summary="Estado del video del evento",
)
def ver_video(
    id_evento: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_actual),
) -> VideoEvento:
    """Mientras está `procesando`, cada consulta le pregunta a Cloudinary.

    Con los archivos ya borrados, o desde el día del borrado, 410: el video
    tampoco existe más."""
    evento = evento_del_usuario(id_evento, db, usuario)
    _exigir_archivos(evento)

    if evento.video_estado == "procesando" and evento.video_public_id:
        url = consultar_video(evento.video_public_id)
        if url:
            evento.video_estado = "listo"
            evento.video_url = url
            _guardar_o_404(db)
        elif evento.video_pedido_en and datetime.now(timezone.utc) - evento.video_pedido_en > _PLAZO_VIDEO:
            log.warning("video %s: Cloudinary no lo terminó en %s", evento.video_public_id, _PLAZO_VIDEO)
            evento.video_estado = "fallo"
            _guardar_o_404(db)

    return _como_video(evento)


@protegido.post(
    "/eventos/{id_evento}/video",
    response_model=VideoEvento,
    status_code=202,
    responses={
        **_ERROR_404_EVENTO,
        **_ERROR_410,
        422: {"model": RespuestaError, "description": "DATOS_INVALIDOS"},
    },
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

    Con los archivos ya borrados, o desde el día del borrado, 410: no quedan
    fotos con qué armarlo.

    La fila del evento se toma ANTES de pedirle nada a Cloudinary y hasta el
    commit (`_tomar_evento_del_usuario`), porque el video aparece en la carpeta
    del evento minutos después del pedido:
    - si borrar_evento lo tiene tomado, esto espera y da 404 sin pedir nada: un
      video pedido para un evento ya borrado quedaría en Cloudinary para siempre;
    - si esto lo tiene, el borrado espera, ve `procesando` y responde 422;
    - dos pedidos a la vez (doble clic): el segundo espera y devuelve el que
      está en curso, sin gastar créditos dos veces.
    """
    evento = _tomar_evento_del_usuario(id_evento, db, usuario)
    _exigir_archivos(evento)

    if _video_en_curso(evento):
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
    responses={**_ERROR_404_EVENTO, **_ERROR_410, 200: {"content": {"application/zip": {}}}},
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

    Con los archivos ya borrados de Cloudinary, 410: el ZIP saldría vacío. Lo
    mismo desde el día del borrado (ver `_exigir_archivos`). Si igual falta
    alguna foto (Cloudinary no la dio), el ZIP lo dice adentro: ver armar_zip.
    """
    evento = evento_del_usuario(id_evento, db, usuario)
    _exigir_archivos(evento)

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


# ─────────────────────────────────────────────────────────────
# Borrar un evento del Historial — sólo admins y superadmins
# ─────────────────────────────────────────────────────────────

_SOLO_DEL_HISTORIAL = (
    "Sólo se pueden borrar eventos del Historial. Si sigue abierto, terminalo primero."
)
_NOMBRE_NO_COINCIDE = "El nombre no coincide con el del evento"
_NO_SE_BORRARON_LAS_FOTOS = "No pudimos borrar las fotos. Probá de nuevo en un rato."
_VIDEO_EN_CURSO = "Se está armando el video de este evento. Probá de nuevo en unos minutos."


def _nombre_comparable(nombre: str) -> str:
    """El nombre como se ve en pantalla, sin mayúsculas: tildes en una sola
    forma (NFC: una "é" pegada desde macOS viene en dos caracteres), sin
    espacios alrededor y con los de adentro juntados en uno. El navegador junta
    los espacios al mostrar el nombre, así que un espacio doble no se ve ni se
    puede copiar, y en el celular dos espacios seguidos escriben ". ".

    Es exactamente lo que hace el diálogo del panel (`normalizar` de
    comp/Confirmar.tsx: NFC, trim, cada tramo de espacios a uno, toLowerCase).
    `lower` y no `casefold`, para no aceptar acá algo que el panel no habilita."""
    return " ".join(unicodedata.normalize("NFC", nombre).split()).lower()


@protegido.delete(
    "/eventos/{id_evento}",
    response_model=EventoBorrado,
    responses={
        **_ERROR_403,
        **_ERROR_404_EVENTO,
        422: {"model": RespuestaError,
              "description": "DATOS_INVALIDOS: el evento no es del Historial, el nombre no "
                             "coincide, se está armando su video o el cuerpo está mal "
                             "formado"},
        503: {"model": RespuestaError,
              "description": "DATOS_INVALIDOS: Cloudinary no pudo borrar las fotos; "
                             "no se borró nada"},
    },
    summary="Borrar un evento del Historial para siempre (admin o superadmin)",
)
def borrar_evento(
    id_evento: int,
    pedido: PedidoBorrarEvento,
    db: Session = Depends(get_db),
    actor: Usuario = Depends(solo_admin),
) -> EventoBorrado:
    """La segunda excepción a "nada se borra" (regla 7), junto con eliminar una
    cuenta. Sólo admins y superadmins, sobre eventos de cualquier cuenta; un
    organizador recibe 403 aunque el evento sea suyo y aunque falte el cuerpo.

    Sólo eventos del Historial, con el mismo criterio que el listado
    (`del_historial`): terminados, o sin publicar de fecha pasada. Uno abierto,
    de cualquier fecha, o uno sin publicar de hoy en adelante → 422. Además
    `confirmar_nombre` tiene que ser el nombre del evento, comparado como se ve
    (`_nombre_comparable`), y no vacío, o 422. Y si Cloudinary está armando su
    video, 422: ver abajo. En cada rechazo no se toca nada.

    Un video en curso (`procesando`, pedido hace menos de `_PLAZO_VIDEO`)
    aparece en la carpeta del evento minutos DESPUÉS del pedido. Si el borrado
    por prefijo pasara antes, el MP4, armado con fotos de invitados, quedaría
    publicado en Cloudinary sin ninguna fila que lo recuerde: ninguna pasada de
    limpieza vuelve a mirar la carpeta de un evento que ya no existe. Por eso se
    le pregunta a Cloudinary: si ya está (nadie lo consultó todavía), se sigue y
    el borrado por prefijo lo alcanza, aunque las fotos ya se hubieran borrado a
    los 30 días; si no, 422 y se prueba en unos minutos.

    Qué se borra: el evento y TODO lo suyo. Si sus archivos todavía no se
    borraron (`fotos_borradas_en` en NULL), primero se borran de Cloudinary
    todas sus imágenes y todos sus videos, con el mismo borrado por prefijo
    exacto de la limpieza a los 30 días (`eventos/{codigo_publico}/`, con la
    barra final). Si Cloudinary falla, no se borra nada de la base y responde
    503: se puede volver a intentar, porque borrar lo que ya no está no es
    error. Después, en una transacción, se borran las filas de sus fotos y la
    del evento (`fotos.evento_id` es la única clave foránea hacia `eventos`), y
    los códigos cortos de vinculación que tuviera vivos (viven en memoria).

    La fila del evento se toma con FOR UPDATE antes de mirar nada, y el lock
    dura hasta el final, Cloudinary incluido:
    - la pasada de limpieza toma los eventos con SKIP LOCKED, así que mientras
      tanto lo saltea; y si la pasada lo tenía tomado primero, esto espera a
      que termine y ve su `fotos_borradas_en`: nunca se pide dos veces el
      borrado ni se marca un evento que ya no existe;
    - dos borrados a la vez del mismo evento: el segundo espera y responde 404;
    - el alta de una foto (FOR KEY SHARE, por la clave foránea) espera y
      después falla: no queda ninguna fila colgada de un evento borrado;
    - armar_video toma la fila antes de pedir el video: si lo tiene él, esto
      espera y ve `procesando`; si lo tiene esto, armar_video espera y da 404
      sin pedirle nada a Cloudinary.

    Después, el código público y el token de pantalla responden 404: el evento
    ya no existe. El log lleva ids, nunca el nombre del evento ni emails.
    """
    fila = db.execute(
        select(Evento, del_historial(hoy_en_argentina()).label("del_historial"))
        .where(Evento.id == id_evento)
        .with_for_update()
    ).first()
    if fila is None:
        raise ErrorApp(Codigo.EVENTO_NO_ENCONTRADO)
    evento, es_del_historial = fila
    if not es_del_historial:
        raise ErrorApp(Codigo.DATOS_INVALIDOS, _SOLO_DEL_HISTORIAL)
    escrito = _nombre_comparable(pedido.confirmar_nombre)
    # Vacío nunca coincide: un evento de nombre en blanco (de antes de
    # NombreEvento) no se borra con un campo vacío, sin escribir nada.
    if not escrito or escrito != _nombre_comparable(evento.nombre):
        raise ErrorApp(Codigo.DATOS_INVALIDOS, _NOMBRE_NO_COINCIDE)

    llamar_a_cloudinary = evento.fotos_borradas_en is None
    if _video_en_curso(evento):
        if not evento.video_public_id or consultar_video(evento.video_public_id) is None:
            raise ErrorApp(Codigo.DATOS_INVALIDOS, _VIDEO_EN_CURSO)
        # Ya está en la carpeta: el borrado por prefijo lo alcanza. También si
        # las fotos ya se habían borrado (el video terminó después de la pasada).
        llamar_a_cloudinary = True

    id_actor = actor.id
    archivos: int | None = None  # None: no hizo falta llamar a Cloudinary
    if llamar_a_cloudinary:
        try:
            archivos = borrar_archivos_del_evento(evento.codigo_publico)
        except ErrorBorrado as e:
            # Suelta el lock enseguida; el mensaje de ErrorBorrado nunca lleva el
            # secreto, sólo el código HTTP y el principio de la respuesta.
            db.rollback()
            log_eventos.error(
                "eventos: la cuenta %s no pudo borrar el evento %s: Cloudinary falló (%s); "
                "no se borró nada de la base",
                id_actor, id_evento, e,
            )
            raise ErrorApp(Codigo.DATOS_INVALIDOS, _NO_SE_BORRARON_LAS_FOTOS, http=503) from e

    # Con el evento tomado no puede entrar ninguna foto nueva: lo que se borra
    # acá es exactamente lo que tenía. Las fotos van antes a propósito, aunque
    # la clave foránea tenga ON DELETE CASCADE: así el número sale del DELETE.
    fotos = db.execute(
        delete(Foto).where(Foto.evento_id == id_evento).execution_options(
            synchronize_session=False
        )
    ).rowcount
    db.execute(
        delete(Evento).where(Evento.id == id_evento).execution_options(
            synchronize_session=False
        )
    )
    db.commit()
    vinculacion.anular_del_evento(id_evento)

    log_eventos.info(
        "eventos: la cuenta %s borró el evento %s con %s fotos; %s",
        id_actor, id_evento, fotos,
        "ya no tenía archivos en Cloudinary" if archivos is None
        else f"{archivos} archivos borrados de Cloudinary",
    )
    return EventoBorrado(eliminado=True, fotos=fotos)
