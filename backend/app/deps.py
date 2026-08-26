"""Dependencias compartidas: quién pide y sobre qué evento.

`evento_por_codigo` y `evento_por_token` son las dos puertas de entrada
públicas. Cada una acota por su clave, y de ahí sale el aislamiento entre
eventos simultáneos: ninguna consulta se hace por el id interno.
"""

from __future__ import annotations

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .errores import Codigo, ErrorApp
from .models import Administrador, Evento
from .security import leer_token

_esquema_bearer = HTTPBearer(auto_error=False)


def admin_actual(
    credenciales: HTTPAuthorizationCredentials | None = Depends(_esquema_bearer),
    db: Session = Depends(get_db),
) -> Administrador:
    if credenciales is None or not credenciales.credentials:
        raise ErrorApp(Codigo.NO_AUTORIZADO)
    admin_id = leer_token(credenciales.credentials)
    admin = db.get(Administrador, admin_id)
    if admin is None:
        raise ErrorApp(Codigo.NO_AUTORIZADO)
    return admin


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


def evento_del_admin(id_evento: int, db: Session, admin: Administrador) -> Evento:
    """Acota por administrador: nadie modera los eventos de otro."""
    evento = db.get(Evento, id_evento)
    if evento is None or evento.admin_id != admin.id:
        raise ErrorApp(Codigo.EVENTO_NO_ENCONTRADO)
    return evento
