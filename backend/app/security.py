"""Contraseñas y tokens de sesión. Sólo para las cuentas del panel.

Los invitados no tienen cuenta ni login: se identifican por `dispositivo_hash`,
sin pedirles datos.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext

from .config import obtener_config
from .errores import Codigo, ErrorApp

config = obtener_config()

# El costo de bcrypt: 2^10 vueltas. Es el ÚNICO lugar donde se fija.
#
# Hasta el 27-sep-2026 era 12, el que passlib usa si no se le dice nada. En
# Render gratuito (0,1 de CPU) el login tardaba 1,9 a 3,7 s con el servicio
# despierto, contra 0,3 s de /api/salud: casi todo era bcrypt. En la máquina
# de desarrollo, 272 ms con 12 y 68 ms con 10: cada ronda menos divide el
# tiempo por dos. 10 es el mínimo que recomienda OWASP para bcrypt, y los
# topes de intentos del login (routers/admin.py) compensan la diferencia.
#
# Con el mínimo y el máximo iguales a este valor, passlib considera que un hash
# con otro costo "necesita actualización": los de 12 que ya están en la base
# se rehacen con 10 la próxima vez que su cuenta entra (ver el login). Todo lo
# que hashea pasa por `hashear_password`: registro, restablecer, cambiar la
# contraseña, crear_admin.py y el hash de relleno del login.
RONDAS_BCRYPT = 10

_contexto = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__default_rounds=RONDAS_BCRYPT,
    bcrypt__min_rounds=RONDAS_BCRYPT,
    bcrypt__max_rounds=RONDAS_BCRYPT,
)

# passlib 1.7.4 busca la versión de bcrypt en `bcrypt.__about__`, que bcrypt 4
# ya no tiene, y deja un traceback "(trapped) error reading bcrypt version" en
# el log con el primer login de cada arranque. Es inofensivo (sigue usando
# bcrypt igual), pero en los logs de Render parece una falla del login.
logging.getLogger("passlib.handlers.bcrypt").setLevel(logging.ERROR)

ALGORITMO = "HS256"


def hashear_password(password: str) -> str:
    """bcrypt con RONDAS_BCRYPT."""
    return _contexto.hash(password)


def verificar_password(password: str, password_hash: str) -> bool:
    """Valida también los hashes con otro costo (los de 12 de antes)."""
    try:
        return _contexto.verify(password, password_hash)
    except ValueError:
        # Hash con un formato que passlib no reconoce: no es una excepción del
        # servidor, es simplemente una credencial que no valida.
        return False


def hash_desactualizado(password_hash: str) -> bool:
    """True si el hash no tiene el costo de RONDAS_BCRYPT. No corre bcrypt:
    lee el costo del propio hash (`$2b$12$…`), así que no tarda nada."""
    try:
        return _contexto.needs_update(password_hash)
    except ValueError:
        return False


def verificar_y_actualizar(password: str, password_hash: str) -> tuple[bool, str | None]:
    """Como `verificar_password`, y además el hash nuevo que hay que guardar.

    Devuelve `(False, None)` si la contraseña no verifica: nunca hay un hash
    nuevo sin la contraseña correcta. `(True, None)` si verifica y el hash ya
    tiene el costo de hoy. `(True, hash_nuevo)` si verifica y el hash tenía
    otro costo: `hash_nuevo` es la misma contraseña con RONDAS_BCRYPT.
    """
    try:
        return _contexto.verify_and_update(password, password_hash)
    except ValueError:
        return False, None


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
