"""Cuentas del panel: registro público y gestión por parte de un admin.

Las cuentas se crean solas desde el registro y nacen `organizador` y
`pendiente`. Ningún admin crea cuentas con contraseña ni conoce contraseñas
ajenas.

Quién gestiona a quién (la matriz completa está en `_exigir_permiso`):

- Un admin o un superadmin habilita, da de baja, reactiva, renombra y hace
  admin a cualquier organizador, esté pendiente, activo o de baja.
- Sólo un superadmin gestiona a los admins: les cambia el rol a organizador,
  los da de baja, los reactiva y los renombra.
- Al superadmin no lo toca nadie desde el panel, ni otro superadmin. Tampoco
  se nombra desde acá: se hace a mano con un UPDATE en la base.

Nada se borra: dar de baja es un estado. La cuenta no puede entrar, pero sus
eventos y fotos quedan, los admins los siguen viendo y se puede reactivar.

`eliminar_cuenta` es una de las dos excepciones a la regla 7 (la otra es
borrar un evento del Historial), sólo para superadmins: borra la fila de la
cuenta para siempre y sus eventos pasan a quien la elimina (ver el docstring
del endpoint).

Nadie cambia su propio rol ni su propio estado. Así el sistema nunca se queda
sin admins por un clic de más, y nadie se bloquea solo. El nombre propio sí.

"Olvidé mi contraseña" también vive acá, en el router público: `recuperar`
manda un link por email (Brevo, app/email.py) y `restablecer` lo canjea por
una contraseña nueva. El resto de Mi cuenta está en routers/admin.py.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, Request, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import email as correo
from ..cloudinary_service import borrar_avatares_de_la_cuenta
from ..database import get_db
from ..deps import es_superadmin, solo_admin, solo_superadmin
from ..errores import Codigo, ErrorApp
from ..models import Evento, Foto, RecuperacionContrasena, Usuario
from ..ratelimit import ip_del_pedido, limpiar_cada_tanto, permitido, permitido_en_todas
from ..schemas import (
    CambioCuenta,
    ContrasenaRestablecida,
    Cuenta,
    CuentaEliminada,
    PedidoEliminarCuenta,
    PedidoRecuperar,
    PedidoRegistro,
    PedidoRestablecer,
    RecuperacionPedida,
    RegistroRecibido,
    RespuestaError,
)
from ..security import (
    al_milisegundo,
    generar_token_recuperacion,
    hash_de_token,
    hashear_password,
)

# Hijo del de uvicorn, que en Render sale en el log a nivel INFO (el de
# `app.*` sólo mostraría los errores). Los mensajes empiezan con "cuentas:"
# porque el log de uvicorn no muestra el nombre del logger.
log = logging.getLogger("uvicorn.error").getChild("cuentas")

# El registro es público: sin tope, un script llena la tabla de cuentas
# pendientes. Cinco por hora y por IP alcanzan para una persona que se equivoca
# y vuelve a probar, y cortan a cualquiera que lo haga en serie.
MAXIMO_REGISTROS = 5
VENTANA_REGISTROS = 3600
# No puede coincidir con un código público: esos miden 8 y no llevan barras.
_CLAVE_REGISTRO = "cuentas/registro"

publico = APIRouter(prefix="/api/cuentas", tags=["cuentas"])
administracion = APIRouter(
    prefix="/api/admin/cuentas",
    tags=["cuentas"],
    dependencies=[Depends(solo_admin)],
    responses={
        401: {"model": RespuestaError, "description": "NO_AUTORIZADO"},
        403: {"model": RespuestaError,
              "description": "NO_AUTORIZADO: la cuenta no es admin ni superadmin"},
    },
)

_SIN_PERMISO = "No tenés permiso para esto"


# ─────────────────────────────────────────────────────────────
# Registro público
# ─────────────────────────────────────────────────────────────

@publico.post(
    "/registro",
    response_model=RegistroRecibido,
    status_code=status.HTTP_201_CREATED,
    responses={
        422: {"model": RespuestaError, "description": "DATOS_INVALIDOS"},
        429: {"model": RespuestaError, "description": "DEMASIADOS_PEDIDOS"},
    },
    summary="Pedir una cuenta de organizador",
)
def registrar(
    pedido: PedidoRegistro, request: Request, db: Session = Depends(get_db)
) -> RegistroRecibido:
    """Responde SIEMPRE 201 `{"estado": "pendiente"}`, también si el email ya
    existe: en ese caso no crea ni cambia nada. Una respuesta distinta serviría
    para averiguar qué emails están registrados.

    Por la misma razón el hash se calcula ANTES de mirar si el email existe:
    bcrypt tarda (unos 70 ms con 10 rondas; en Render gratuito, bastante más),
    y si sólo corriera para los emails nuevos, el tiempo de respuesta delataría
    a los que ya están.
    """
    if not permitido(
        ip_del_pedido(request), _CLAVE_REGISTRO,
        maximo=MAXIMO_REGISTROS, ventana=VENTANA_REGISTROS,
    ):
        raise ErrorApp(Codigo.DEMASIADOS_PEDIDOS)
    limpiar_cada_tanto()

    password_hash = hashear_password(pedido.password)
    existente = db.scalar(select(Usuario.id).where(func.lower(Usuario.email) == pedido.email))
    if existente is None:
        db.add(
            Usuario(
                email=pedido.email,
                nombre=pedido.nombre,
                password_hash=password_hash,
                rol="organizador",
                estado="pendiente",
            )
        )
        try:
            db.commit()
        except IntegrityError:
            # Dos registros del mismo email a la vez: el UNIQUE deja pasar uno
            # y el otro recibe la misma respuesta que un email repetido.
            db.rollback()
    return RegistroRecibido(estado="pendiente")


# ─────────────────────────────────────────────────────────────
# Olvidé mi contraseña — público
# ─────────────────────────────────────────────────────────────

# El link del email sirve una vez y durante una hora.
VIGENCIA_RECUPERACION = timedelta(hours=1)

# Topes por hora. Por IP frena a un script que recorre emails; por email, a
# quien le llena la casilla a otra persona desde muchas IPs. Tres alcanzan para
# quien no encuentra el email y lo vuelve a pedir. Cuentan igual exista o no
# la cuenta: el 429 no delata nada.
MAXIMO_RECUPERACIONES_POR_IP = 5
MAXIMO_RECUPERACIONES_POR_EMAIL = 3
VENTANA_RECUPERACION = 3600
# Restablecer: el token tiene 256 bits y no se adivina, pero sin tope cada
# intento con uno válido cuesta un bcrypt.
MAXIMO_RESTABLECER_POR_IP = 10
VENTANA_RESTABLECER = 3600
# No pueden coincidir con una IP ni con un código público: llevan una barra.
_CLAVE_RECUPERAR = "cuentas/recuperar"
_CLAVE_RESTABLECER = "cuentas/restablecer"

_LINK_VENCIDO = "El link ya no sirve. Pedí uno nuevo."


def anular_recuperaciones(
    db: Session, usuario_id: int, ahora: datetime, excepto: int | None = None
) -> None:
    """Anula los pedidos de recuperación que seguían vivos de la cuenta. Lo usan
    un pedido nuevo (sólo el último link sirve), restablecer y cambiar la
    contraseña desde Mi cuenta (un link viejo no puede pisar la contraseña
    nueva). No confirma: va en la transacción de quien llama.

    `excepto` es el pedido que se está usando: la sesión no hace autoflush, así
    que su `usado_en` todavía no llegó a la base y este UPDATE lo anularía."""
    condiciones = [
        RecuperacionContrasena.usuario_id == usuario_id,
        RecuperacionContrasena.usado_en.is_(None),
        RecuperacionContrasena.anulado_en.is_(None),
        RecuperacionContrasena.vence_en > ahora,
    ]
    if excepto is not None:
        condiciones.append(RecuperacionContrasena.id != excepto)
    db.execute(update(RecuperacionContrasena).where(*condiciones).values(anulado_en=ahora))


@publico.post(
    "/recuperar",
    response_model=RecuperacionPedida,
    responses={
        422: {"model": RespuestaError, "description": "DATOS_INVALIDOS: no tiene forma de email"},
        429: {"model": RespuestaError, "description": "DEMASIADOS_PEDIDOS"},
    },
    summary="Olvidé mi contraseña: pedir el link por email",
)
def recuperar(
    pedido: PedidoRecuperar,
    request: Request,
    tareas: BackgroundTasks,
    db: Session = Depends(get_db),
) -> RecuperacionPedida:
    """Responde SIEMPRE 200 `{"enviado": true}`, exista o no la cuenta: una
    respuesta distinta serviría para averiguar qué emails están registrados.

    Sólo si la cuenta existe y está `activa` se genera un token, se guarda su
    hash con vencimiento en una hora, se anulan los pedidos anteriores que
    seguían vivos y se manda el email. A una cuenta pendiente o de baja no le
    llega nada: no podría entrar aunque cambiara la contraseña.

    El email sale en segundo plano, después de la respuesta: esperar a Brevo
    haría que la respuesta tarde más justo cuando la cuenta existe.

    La fila de la cuenta se toma con FOR NO KEY UPDATE: dos pedidos a la vez de
    la misma cuenta se hacen de a uno, y siempre queda un solo link vivo.
    """
    email = pedido.email
    if not permitido_en_todas(
        [
            ((ip_del_pedido(request), _CLAVE_RECUPERAR), MAXIMO_RECUPERACIONES_POR_IP),
            ((_CLAVE_RECUPERAR, email), MAXIMO_RECUPERACIONES_POR_EMAIL),
        ],
        ventana=VENTANA_RECUPERACION,
    ):
        raise ErrorApp(Codigo.DEMASIADOS_PEDIDOS)
    limpiar_cada_tanto()

    usuario = db.scalar(
        select(Usuario)
        .where(func.lower(Usuario.email) == email)
        .with_for_update(key_share=True)
    )
    if usuario is not None and usuario.estado == "activa":
        ahora = datetime.now(timezone.utc)
        token = generar_token_recuperacion()
        anular_recuperaciones(db, usuario.id, ahora)
        db.add(RecuperacionContrasena(
            usuario_id=usuario.id,
            token_hash=hash_de_token(token),
            creado_en=ahora,
            vence_en=ahora + VIGENCIA_RECUPERACION,
        ))
        db.commit()
        tareas.add_task(correo.enviar_recuperacion, usuario.email, usuario.nombre, token, usuario.id)
    else:
        db.rollback()
    return RecuperacionPedida(enviado=True)


@publico.post(
    "/restablecer",
    response_model=ContrasenaRestablecida,
    responses={
        422: {"model": RespuestaError,
              "description": "DATOS_INVALIDOS: el link ya no sirve, o la contraseña no tiene "
                             "entre 10 y 128 caracteres"},
        429: {"model": RespuestaError, "description": "DEMASIADOS_PEDIDOS"},
    },
    summary="Olvidé mi contraseña: elegir una nueva con el link del email",
)
def restablecer(
    pedido: PedidoRestablecer, request: Request, db: Session = Depends(get_db)
) -> ContrasenaRestablecida:
    """Un token inexistente, vencido, usado, anulado o de una cuenta que ya no
    está activa responde SIEMPRE lo mismo: 422 "El link ya no sirve. Pedí uno
    nuevo." Distinguirlos no le sirve a quien lo usa y sí a quien prueba.

    Si sirve: cambia la contraseña, marca el pedido como usado y cierra TODAS
    las sesiones abiertas de la cuenta (`sesiones_desde`). Después hay que
    entrar de nuevo con la contraseña nueva.

    El pedido se toma con FOR UPDATE: dos canjes a la vez del mismo link se
    hacen de a uno, y el segundo ya lo encuentra usado.
    """
    if not permitido(
        ip_del_pedido(request), _CLAVE_RESTABLECER,
        maximo=MAXIMO_RESTABLECER_POR_IP, ventana=VENTANA_RESTABLECER,
    ):
        raise ErrorApp(Codigo.DEMASIADOS_PEDIDOS)
    limpiar_cada_tanto()

    ahora = datetime.now(timezone.utc)
    recuperacion = db.scalar(
        select(RecuperacionContrasena)
        .where(RecuperacionContrasena.token_hash == hash_de_token(pedido.token))
        .with_for_update()
    )
    if (
        recuperacion is None
        or recuperacion.usado_en is not None
        or recuperacion.anulado_en is not None
        or recuperacion.vence_en <= ahora
    ):
        raise ErrorApp(Codigo.DATOS_INVALIDOS, _LINK_VENCIDO)
    usuario = db.get(Usuario, recuperacion.usuario_id, with_for_update={"key_share": True})
    if usuario is None or usuario.estado != "activa":
        raise ErrorApp(Codigo.DATOS_INVALIDOS, _LINK_VENCIDO)

    usuario.password_hash = hashear_password(pedido.password)
    momento = al_milisegundo(datetime.now(timezone.utc))
    usuario.sesiones_desde = momento
    recuperacion.usado_en = momento
    anular_recuperaciones(db, usuario.id, momento, excepto=recuperacion.id)
    db.commit()
    log.info("cuentas: la cuenta %s restableció su contraseña con el link del email", usuario.id)
    return ContrasenaRestablecida(restablecida=True)


# ─────────────────────────────────────────────────────────────
# Gestión de cuentas — sólo admins y superadmins
# ─────────────────────────────────────────────────────────────

_ORDEN_ESTADO = {"pendiente": 0, "activa": 1, "baja": 2}


def _historiales(db: Session, ids: list[int]) -> dict[int, tuple[int, date | None]]:
    """Cantidad de eventos y fecha del más reciente de cada cuenta, en una consulta."""
    if not ids:
        return {}
    filas = db.execute(
        select(Evento.usuario_id, func.count(Evento.id), func.max(Evento.fecha_evento))
        .where(Evento.usuario_id.in_(ids))
        .group_by(Evento.usuario_id)
    ).all()
    return {usuario_id: (cantidad, ultima) for usuario_id, cantidad, ultima in filas}


def _como_cuenta(usuario: Usuario, historial: tuple[int, date | None] | None) -> Cuenta:
    eventos, ultimo_evento = historial or (0, None)
    return Cuenta(
        id=usuario.id,
        email=usuario.email,
        nombre=usuario.nombre,
        rol=usuario.rol,
        estado=usuario.estado,
        creado_en=usuario.creado_en,
        eventos=eventos,
        ultimo_evento=ultimo_evento,
        avatar_url=usuario.avatar_url,
    )


def _orden(usuario: Usuario) -> tuple:
    """Pendientes primero y las más nuevas arriba: son las que esperan respuesta.
    Después las activas y al final las de baja, cada grupo por nombre."""
    grupo = _ORDEN_ESTADO[usuario.estado]
    if usuario.estado == "pendiente":
        return (grupo, -usuario.creado_en.timestamp(), -usuario.id)
    return (grupo, usuario.nombre.casefold(), usuario.id)


@administracion.get("", response_model=list[Cuenta], summary="Listar cuentas")
def listar_cuentas(db: Session = Depends(get_db)) -> list[Cuenta]:
    usuarios = sorted(db.scalars(select(Usuario)), key=_orden)
    historiales = _historiales(db, [u.id for u in usuarios])
    return [_como_cuenta(u, historiales.get(u.id)) for u in usuarios]


def _exigir_permiso(actor: Usuario, cuenta: Usuario, cambio: CambioCuenta) -> None:
    """Quién puede cambiar qué cuenta. El actor ya es admin o superadmin.

    | objetivo                         | admin | superadmin |
    |----------------------------------|-------|------------|
    | organizador (pendiente, activa   |  sí   |     sí     |
    | o de baja): rol, estado, nombre  |       |            |
    | admin: rol, estado, nombre       |  403  |     sí     |
    | superadmin: cualquier campo      |  403  |    403     |
    | la propia: rol o estado          |  422  |    422     |
    | la propia: nombre                |  sí   |     sí     |

    Y `rol: superadmin` es 422 siempre, sea cual sea la cuenta: ese rol no se
    asigna desde el panel.

    Se decide por lo que la cuenta ES, no por lo que se le pide: un admin no
    puede ni renombrar a otro admin, aunque sea con el nombre que ya tiene. El
    permiso no depende de si el cambio termina tocando algo.
    """
    if cambio.rol == "superadmin":
        raise ErrorApp(Codigo.DATOS_INVALIDOS, "El rol superadmin no se asigna desde el panel")
    if cuenta.id == actor.id:
        if cambio.rol is not None or cambio.estado is not None:
            raise ErrorApp(Codigo.DATOS_INVALIDOS, "No podés cambiar tu propio rol ni tu estado")
        return
    if cuenta.rol == "superadmin":
        raise ErrorApp(Codigo.NO_AUTORIZADO, _SIN_PERMISO, http=403)
    if cuenta.rol == "admin" and not es_superadmin(actor):
        raise ErrorApp(Codigo.NO_AUTORIZADO, _SIN_PERMISO, http=403)


@administracion.patch(
    "/{id_cuenta}",
    response_model=Cuenta,
    responses={
        403: {"model": RespuestaError,
              "description": "NO_AUTORIZADO: la cuenta es de un admin o de un superadmin"},
        404: {"model": RespuestaError, "description": "DATOS_INVALIDOS: la cuenta no existe"},
        422: {"model": RespuestaError, "description": "DATOS_INVALIDOS"},
    },
    summary="Habilitar, dar de baja, cambiar el rol o el nombre de una cuenta",
)
def cambiar_cuenta(
    id_cuenta: int,
    cambio: CambioCuenta,
    db: Session = Depends(get_db),
    actor: Usuario = Depends(solo_admin),
) -> Cuenta:
    """Idempotente: si no cambia nada, no se toca nada.

    Sobre la propia cuenta sólo se puede cambiar el nombre. Con el rol o el
    estado propios se podría dejar el sistema sin admins, o bloquearse solo.
    Un admin gestiona organizadores; a los admins, sólo un superadmin; al
    superadmin, nadie (ver `_exigir_permiso`).
    """
    cuenta = db.get(Usuario, id_cuenta)
    if cuenta is None:
        raise ErrorApp(Codigo.DATOS_INVALIDOS, "No encontramos esa cuenta", http=404)
    _exigir_permiso(actor, cuenta, cambio)

    cambio_algo = False
    for campo in ("estado", "rol", "nombre"):
        valor = getattr(cambio, campo)
        if valor is not None and valor != getattr(cuenta, campo):
            setattr(cuenta, campo, valor)
            cambio_algo = True
    if cambio_algo:
        db.commit()
        db.refresh(cuenta)

    return _como_cuenta(cuenta, _historiales(db, [cuenta.id]).get(cuenta.id))


# ─────────────────────────────────────────────────────────────
# Eliminar una cuenta para siempre — sólo superadmins
# ─────────────────────────────────────────────────────────────

_ELIMINAR_SUPERADMIN = "A una cuenta superadmin no se la elimina desde el panel"
_ELIMINAR_PROPIA = "No podés eliminar tu propia cuenta"
_EMAIL_NO_COINCIDE = "El email no coincide con el de la cuenta"


def _email_comparable(email: str) -> str:
    """Sin espacios alrededor y sin mayúsculas: lo mismo que hace el diálogo del panel."""
    return email.strip().lower()


@administracion.delete(
    "/{id_cuenta}",
    response_model=CuentaEliminada,
    responses={
        403: {"model": RespuestaError,
              "description": "NO_AUTORIZADO: quien pide no es superadmin, "
                             "o la cuenta es de un superadmin"},
        404: {"model": RespuestaError, "description": "DATOS_INVALIDOS: la cuenta no existe"},
        422: {"model": RespuestaError,
              "description": "DATOS_INVALIDOS: es la propia cuenta, el email no coincide "
                             "o el cuerpo está mal formado"},
    },
    summary="Eliminar una cuenta para siempre (sólo superadmin)",
)
def eliminar_cuenta(
    id_cuenta: int,
    pedido: PedidoEliminarCuenta,
    tareas: BackgroundTasks,
    db: Session = Depends(get_db),
    actor: Usuario = Depends(solo_superadmin),
) -> CuentaEliminada:
    """Una de las dos excepciones a "nada se borra" (regla 7; la otra es borrar
    un evento del Historial), y sólo para superadmins.

    Se borra la fila de `usuarios` y nada más: el nombre, el email y la
    contraseña (y con ella sus pedidos de recuperación de contraseña, por ON
    DELETE CASCADE). Los eventos de la cuenta, con sus fotos y videos, pasan a
    la cuenta del superadmin que la elimina; en `fotos.moderada_por`, lo que
    moderó queda en NULL. Las tres cosas en una sola transacción: o pasa todo,
    o no pasa nada.

    Si tenía avatar, después de confirmar se borra de Cloudinary todo
    `avatares/{id}/`, en segundo plano y a mejor esfuerzo: si Cloudinary falla,
    queda en el log y la cuenta igual está eliminada.

    | objetivo                                   | admin u organizador | superadmin |
    |--------------------------------------------|---------------------|------------|
    | organizador (pendiente, activa o de baja)  |         403         |    200     |
    | admin (activo o de baja)                   |         403         |    200     |
    | otro superadmin                            |         403         |    403     |
    | la propia cuenta                           |         403         |    422     |
    | una cuenta que no existe                   |         403         |    404     |

    Además `confirmar_email` tiene que ser el email de la cuenta (sin
    mayúsculas ni espacios alrededor), o 422. En cada rechazo la base queda
    como estaba.

    Después, el token de la cuenta eliminada deja de servir (`usuario_actual`
    no la encuentra) y el email queda libre para registrarse de nuevo. El id no
    se reusa: es IDENTITY, así que un token viejo nunca apunta a la cuenta nueva.

    La fila se toma con FOR UPDATE antes de mirar nada. Un evento nuevo para
    esta cuenta, o una foto que modera en ese momento, necesita FOR KEY SHARE
    sobre la misma fila (clave foránea): espera a que esto termine y no queda
    ninguna referencia colgada que haga fallar el DELETE.
    """
    cuenta = db.get(Usuario, id_cuenta, with_for_update=True)
    if cuenta is None:
        raise ErrorApp(Codigo.DATOS_INVALIDOS, "No encontramos esa cuenta", http=404)
    if cuenta.id == actor.id:
        raise ErrorApp(Codigo.DATOS_INVALIDOS, _ELIMINAR_PROPIA)
    if cuenta.rol == "superadmin":
        raise ErrorApp(Codigo.NO_AUTORIZADO, _ELIMINAR_SUPERADMIN, http=403)
    if _email_comparable(pedido.confirmar_email) != _email_comparable(cuenta.email):
        raise ErrorApp(Codigo.DATOS_INVALIDOS, _EMAIL_NO_COINCIDE)

    id_actor, id_eliminada = actor.id, cuenta.id
    tenia_avatar = cuenta.avatar_public_id is not None
    # RETURNING: después del commit, los eventos transferidos se mezclan con los
    # del superadmin. Sus ids en el log son lo único que permite devolverlos si
    # se eliminó por error (volver a registrar la cuenta y
    # UPDATE eventos SET usuario_id = <nuevo> WHERE id IN (...)).
    ids_eventos = sorted(db.execute(
        update(Evento).where(Evento.usuario_id == id_eliminada)
        .values(usuario_id=id_actor).returning(Evento.id)
    ).scalars().all())
    transferidos = len(ids_eventos)
    db.execute(update(Foto).where(Foto.moderada_por == id_eliminada).values(moderada_por=None))
    db.execute(delete(Usuario).where(Usuario.id == id_eliminada))
    db.commit()

    # Sólo ids: el email y el nombre de la cuenta eliminada no quedan ni en el log.
    log.info(
        "cuentas: la cuenta %s eliminó la cuenta %s; sus %s eventos pasaron a la cuenta %s: %s",
        id_actor, id_eliminada, transferidos, id_actor, ids_eventos,
    )
    if tenia_avatar:
        tareas.add_task(borrar_avatares_de_la_cuenta, id_eliminada)
    return CuentaEliminada(eventos_transferidos=transferidos)
