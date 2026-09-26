"""Contraseñas y tokens de sesión. Sólo para las cuentas del panel.

Los invitados no tienen cuenta ni login: se identifican por `dispositivo_hash`,
sin pedirles datos.
"""

from __future__ import annotations

import hashlib
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


def al_milisegundo(momento: datetime) -> datetime:
    """El mismo instante sin los microsegundos que sobran del milisegundo.

    `iat` y `usuarios.sesiones_desde` se comparan al milisegundo. Al segundo no
    alcanza: una sesión abierta en el mismo segundo en que se cambia la
    contraseña seguiría valiendo. Y con microsegundos, el `iat` no entra entero
    en un número de JSON (un double tiene 15 o 16 cifras).
    """
    return momento.replace(microsecond=momento.microsecond - momento.microsecond % 1000)


def milisegundos(momento: datetime) -> int:
    """Milisegundos desde 1970, exactos para un momento ya truncado."""
    return round(momento.timestamp() * 1000)


def crear_token(
    usuario_id: int, email: str, emitido_en: datetime | None = None
) -> tuple[str, datetime]:
    """Devuelve el token y su vencimiento, que es lo que pide el contrato.

    El token no lleva rol ni estado a propósito: se leen de la base en cada
    pedido, así una baja o un cambio de rol valen en el acto.

    `iat` va con milisegundos (un NumericDate de JWT puede tener decimales).
    Un token con `iat` anterior a `usuarios.sesiones_desde` ya no sirve (ver
    `usuario_actual`). Al cambiar la contraseña, `emitido_en` es exactamente el
    `sesiones_desde` nuevo: la sesión de quien la cambió sigue, las demás no.
    """
    emitido = al_milisegundo(emitido_en or datetime.now(timezone.utc))
    expira_en = emitido + timedelta(hours=config.JWT_HORAS)
    token = jwt.encode(
        {
            "sub": str(usuario_id),
            "email": email,
            "iat": milisegundos(emitido) / 1000,
            "exp": expira_en,
        },
        config.JWT_SECRET,
        algorithm=ALGORITMO,
    )
    return token, expira_en


def leer_sesion(token: str) -> tuple[int, int | None]:
    """Devuelve el id de la cuenta y el `iat` en milisegundos, o levanta NO_AUTORIZADO.

    El `iat` puede faltar (None) sólo en un token armado a mano: todos los que
    emite `crear_token` lo llevan.
    """
    try:
        carga = jwt.decode(token, config.JWT_SECRET, algorithms=[ALGORITMO])
    except jwt.PyJWTError:
        raise ErrorApp(Codigo.NO_AUTORIZADO) from None
    sub = carga.get("sub")
    if sub is None:
        raise ErrorApp(Codigo.NO_AUTORIZADO)
    try:
        usuario_id = int(sub)
    except (TypeError, ValueError):
        raise ErrorApp(Codigo.NO_AUTORIZADO) from None
    iat = carga.get("iat")
    if isinstance(iat, bool) or not isinstance(iat, (int, float)):
        return usuario_id, None
    return usuario_id, round(iat * 1000)


def leer_token(token: str) -> int:
    """Devuelve el id de la cuenta, o levanta NO_AUTORIZADO."""
    return leer_sesion(token)[0]


# ─────────────────────────────────────────────────────────────
# Recuperar la contraseña por email
# ─────────────────────────────────────────────────────────────

def generar_token_recuperacion() -> str:
    """43 caracteres al azar (256 bits). Viaja sólo en el link del email."""
    return secrets.token_urlsafe(32)


def hash_de_token(token: str) -> str:
    """Lo que se guarda en `recuperaciones_contrasena.token_hash`.

    sha256 y no bcrypt: el token ya tiene 256 bits al azar, no hay nada que
    adivinar por fuerza bruta, y así se busca directo por el índice único.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


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
