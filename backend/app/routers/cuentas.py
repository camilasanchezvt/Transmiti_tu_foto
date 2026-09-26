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

Nadie cambia su propio rol ni su propio estado. Así el sistema nunca se queda
sin admins por un clic de más, y nadie se bloquea solo. El nombre propio sí.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import es_superadmin, solo_admin
from ..errores import Codigo, ErrorApp
from ..models import Evento, Usuario
from ..ratelimit import ip_del_pedido, limpiar_cada_tanto, permitido
from ..schemas import CambioCuenta, Cuenta, PedidoRegistro, RegistroRecibido, RespuestaError
from ..security import hashear_password

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
    bcrypt tarda un cuarto de segundo, y si sólo corriera para los emails
    nuevos, el tiempo de respuesta delataría a los que ya están.
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
