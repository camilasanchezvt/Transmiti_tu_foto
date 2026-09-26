"""Dependencias compartidas: quién pide y sobre qué evento.

`evento_por_codigo` y `evento_por_token` son las dos puertas de entrada
públicas. Cada una acota por su clave, y de ahí sale el aislamiento entre
eventos simultáneos: ninguna consulta se hace por el id interno.

Del lado del panel, `usuario_actual` dice quién pide y `evento_del_usuario`
acota por dueño: un admin llega a cualquier evento, un organizador sólo a los
suyos. Para todo lo que no son cuentas, un superadmin es un admin más: la única
diferencia está en routers/cuentas.py, donde además gestiona a los admins y es
el único que elimina una cuenta para siempre (`solo_superadmin`).
"""

from __future__ import annotations

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .errores import Codigo, ErrorApp
from .models import Evento, Usuario
from .security import leer_token

_esquema_bearer = HTTPBearer(auto_error=False)


def usuario_actual(
    credenciales: HTTPAuthorizationCredentials | None = Depends(_esquema_bearer),
    db: Session = Depends(get_db),
) -> Usuario:
    """La cuenta se relee en cada pedido, no se confía en lo que dice el token.

    Así una cuenta dada de baja deja de entrar en el acto, aunque tenga un token
    vigente por doce horas más, y un cambio de rol vale desde el pedido
    siguiente.
    """
    if credenciales is None or not credenciales.credentials:
        raise ErrorApp(Codigo.NO_AUTORIZADO)
    usuario = db.get(Usuario, leer_token(credenciales.credentials))
    if usuario is None or usuario.estado != "activa":
        raise ErrorApp(Codigo.NO_AUTORIZADO)
    return usuario


# Los roles que ven todo. El superadmin es un admin que además gestiona admins.
ROLES_ADMIN = ("superadmin", "admin")


def es_admin(usuario: Usuario) -> bool:
    """Admin o superadmin: ve todos los eventos y todas las cuentas."""
    return usuario.rol in ROLES_ADMIN


def es_superadmin(usuario: Usuario) -> bool:
    return usuario.rol == "superadmin"


_SIN_PERMISO = "No tenés permiso para esto"


def solo_admin(usuario: Usuario = Depends(usuario_actual)) -> Usuario:
    """Admin o superadmin. 403 y no 401: la sesión es válida, lo que falta es permiso."""
    if not es_admin(usuario):
        raise ErrorApp(Codigo.NO_AUTORIZADO, _SIN_PERMISO, http=403)
    return usuario


def solo_superadmin(usuario: Usuario = Depends(usuario_actual)) -> Usuario:
    """Sólo superadmin. Lo usa lo único que un admin no puede hacer: eliminar
    una cuenta para siempre (routers/cuentas.py). Mismo 403 y mismo mensaje que
    `solo_admin`: para quien no llega, da igual qué rol le faltó."""
    if not es_superadmin(usuario):
        raise ErrorApp(Codigo.NO_AUTORIZADO, _SIN_PERMISO, http=403)
    return usuario


def evento_por_codigo(codigo_publico: str, db: Session = Depends(get_db)) -> Evento:
    """Un evento en `borrador` no existe hacia afuera: responde 404."""
    evento = db.scalar(select(Evento).where(Evento.codigo_publico == codigo_publico))
    if evento is None or evento.estado == "borrador":
        raise ErrorApp(Codigo.EVENTO_NO_ENCONTRADO)
    return evento


def evento_por_token(token_pantalla: str, db: Session = Depends(get_db)) -> Evento:
    """Un evento `cerrado` sigue sirviendo la pantalla: las aprobadas terminan de pasar."""
    evento = db.scalar(select(Evento).where(Evento.token_pantalla == token_pantalla))
    if evento is None:
        raise ErrorApp(Codigo.EVENTO_NO_ENCONTRADO)
    if evento.estado == "borrador":
        raise ErrorApp(Codigo.EVENTO_BORRADOR)
    return evento


def evento_del_usuario(id_evento: int, db: Session, usuario: Usuario) -> Evento:
    """Un admin o un superadmin llega a cualquier evento; un organizador, sólo a los suyos.

    El evento ajeno responde 404 y no 403, igual que uno que no existe: un 403
    le confirmaría a un organizador que ese id es un evento de otra persona.
    """
    evento = db.get(Evento, id_evento)
    if evento is None or not (es_admin(usuario) or evento.usuario_id == usuario.id):
        raise ErrorApp(Codigo.EVENTO_NO_ENCONTRADO)
    return evento
