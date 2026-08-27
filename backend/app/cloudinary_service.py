"""Firma de subidas a Cloudinary y validación de lo que el navegador reporta.

El backend nunca ve los bytes de la foto: el navegador sube directo a Cloudinary
con una firma que se pide acá. El CLOUDINARY_API_SECRET no sale de este proceso.

La firma se calcula a mano con hashlib en vez de usar el SDK de Cloudinary,
porque el SDK no está en la lista de dependencias autorizadas (regla 10) y el
algoritmo son cuatro líneas.
"""

from __future__ import annotations

import hashlib
import re
import time
from urllib.parse import urlparse

from .config import obtener_config
from .errores import Codigo, ErrorApp

config = obtener_config()

# Sólo imágenes. Nada de video.
EXTENSIONES_PERMITIDAS = ("jpg", "jpeg", "png", "webp", "heic")
TIPOS_PERMITIDOS = ("image/jpeg", "image/png", "image/webp", "image/heic")

HOST_CLOUDINARY = "res.cloudinary.com"


def carpeta_del_evento(codigo_publico: str) -> str:
    """La carpeta es siempre `eventos/{codigo_publico}`."""
    return f"eventos/{codigo_publico}"


def firmar(codigo_publico: str, momento: int | None = None) -> dict:
    """Firma sólo `folder` y `timestamp`.

    Cloudinary exige que los parámetros firmados coincidan EXACTAMENTE con los
    que el navegador manda en el FormData. Si acá se firma un parámetro de más,
    o el navegador manda uno de más, la subida falla con "Invalid Signature".
    """
    timestamp = int(time.time()) if momento is None else momento
    folder = carpeta_del_evento(codigo_publico)

    # Los parámetros van ordenados alfabéticamente y unidos por &, con el
    # api_secret pegado al final. Después, SHA-1.
    a_firmar = f"folder={folder}&timestamp={timestamp}"
    firma = hashlib.sha1(
        (a_firmar + config.CLOUDINARY_API_SECRET).encode("utf-8")
    ).hexdigest()

    return {
        "cloud_name": config.CLOUDINARY_CLOUD_NAME,
        "api_key": config.CLOUDINARY_API_KEY,
        "timestamp": timestamp,
        "signature": firma,
        "folder": folder,
    }


def verificar_public_id(public_id: str, codigo_publico: str) -> None:
    """Regla 4: el public_id tiene que vivir dentro de la carpeta del evento.

    Sin esta línea, cualquiera puede registrar la URL de una imagen ajena y
    aparece proyectada.
    """
    prefijo = carpeta_del_evento(codigo_publico) + "/"
    if not public_id.startswith(prefijo):
        raise ErrorApp(Codigo.PUBLIC_ID_AJENO)
    resto = public_id[len(prefijo):]
    # Ni vacío, ni con subcarpetas, ni saliendo de la carpeta por las suyas.
    if not resto or "/" in resto or ".." in resto:
        raise ErrorApp(Codigo.PUBLIC_ID_AJENO)


def verificar_url(url: str, public_id: str) -> None:
    """La URL tiene que ser una imagen de Cloudinary que corresponda al public_id.

    El brief sólo pide verificar el public_id, pero el campo que después se
    proyecta es `url`. Si se aceptara cualquier URL, un public_id válido
    alcanzaría para hacer aparecer en la pantalla una imagen alojada en otra
    cuenta de Cloudinary: la verificación de carpeta quedaría sin efecto.
    """
    partes = urlparse(url)
    if partes.scheme != "https" or partes.hostname != HOST_CLOUDINARY:
        raise ErrorApp(Codigo.ARCHIVO_INVALIDO)

    if "/image/upload/" not in partes.path:
        # /video/upload/ y /raw/upload/ quedan afuera: sólo imágenes.
        raise ErrorApp(Codigo.ARCHIVO_INVALIDO)

    if config.CLOUDINARY_CLOUD_NAME:
        if not partes.path.startswith(f"/{config.CLOUDINARY_CLOUD_NAME}/"):
            raise ErrorApp(Codigo.ARCHIVO_INVALIDO)

    if public_id not in partes.path:
        raise ErrorApp(Codigo.ARCHIVO_INVALIDO)

    extension = partes.path.rsplit(".", 1)[-1].lower()
    if extension not in EXTENSIONES_PERMITIDAS:
        raise ErrorApp(Codigo.ARCHIVO_INVALIDO)


_SOLO_SEGURO = re.compile(r"^[A-Za-z0-9_\-]+$")


def public_id_bien_formado(public_id: str) -> bool:
    """El sufijo que genera Cloudinary es alfanumérico. Se usa en las pruebas."""
    prefijo, _, resto = public_id.rpartition("/")
    return bool(prefijo) and bool(_SOLO_SEGURO.match(resto))
