"""Contraseñas y tokens de sesión. Sólo para las cuentas del panel.

Los invitados no tienen cuenta ni login: se identifican por `dispositivo_hash`,
sin pedirles datos.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext

from .config import obtener_config
from .errores import Codigo, ErrorApp

config = obtener_config()

_contexto = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITMO = "HS256"


def hashear_password(password: str) -> str:
    return _contexto.hash(password)


def verificar_password(password: str, password_hash: str) -> bool:
    try:
        return _contexto.verify(password, password_hash)
    except ValueError:
        # Hash con un formato que passlib no reconoce: no es una excepción del
        # servidor, es simplemente una credencial que no valida.
        return False


def crear_token(usuario_id: int, email: str) -> tuple[str, datetime]:
    """Devuelve el token y su vencimiento, que es lo que pide el contrato.

    El token no lleva rol ni estado a propósito: se leen de la base en cada
    pedido, así una baja o un cambio de rol valen en el acto.
    """
    expira_en = datetime.now(timezone.utc) + timedelta(hours=config.JWT_HORAS)
    token = jwt.encode(
        {
            "sub": str(usuario_id),
            "email": email,
            "iat": datetime.now(timezone.utc),
            "exp": expira_en,
        },
        config.JWT_SECRET,
        algorithm=ALGORITMO,
    )
    return token, expira_en


def leer_token(token: str) -> int:
    """Devuelve el id de la cuenta, o levanta NO_AUTORIZADO."""
    try:
        carga = jwt.decode(token, config.JWT_SECRET, algorithms=[ALGORITMO])
    except jwt.PyJWTError:
        raise ErrorApp(Codigo.NO_AUTORIZADO) from None
    sub = carga.get("sub")
    if sub is None:
        raise ErrorApp(Codigo.NO_AUTORIZADO)
    try:
        return int(sub)
    except (TypeError, ValueError):
        raise ErrorApp(Codigo.NO_AUTORIZADO) from None


# ─────────────────────────────────────────────────────────────
# Claves públicas de un evento
# ─────────────────────────────────────────────────────────────

def generar_codigo_publico() -> str:
    """8 caracteres. Va en el QR y sólo habilita a subir fotos."""
    return secrets.token_urlsafe(6)


def generar_token_pantalla() -> str:
    """32 caracteres. Vive en la notebook del proyector y sólo habilita a leer.

    Las dos claves se generan al azar, nunca a partir del id ni de la fecha: si
    fueran adivinables, el aislamiento entre eventos simultáneos no existiría.
    """
    return secrets.token_urlsafe(24)
