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
import zipfile
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


# ─────────────────────────────────────────────────────────────
# Armado del ZIP, en streaming
# ─────────────────────────────────────────────────────────────

class _Chorro:
    """Un archivo de salida que junta lo escrito y lo entrega por pedazos.

    zipfile necesita algo con `write`. Si además tuviera `seek`, escribiría el
    encabezado de cada entrada dos veces (vuelve atrás para completar tamaños);
    al no tenerlo, usa descriptores de datos y nunca necesita retroceder. Eso es
    lo que permite mandar el ZIP mientras se arma, sin tenerlo entero en memoria.
    """

    def __init__(self) -> None:
        self._datos = bytearray()

    def write(self, datos: bytes) -> int:
        self._datos.extend(datos)
        return len(datos)

    def flush(self) -> None:
        pass

    def tomar(self) -> bytes:
        salida = bytes(self._datos)
        self._datos.clear()
        return salida


# Caracteres que no pueden aparecer en un nombre de archivo. La barra y la
# contrabarra son las que importan de verdad: crearían carpetas dentro del ZIP.
# Se arma sin literales escapados a propósito, porque un escape mal puesto acá
# se ve igual que uno bien puesto y falla recién con un nombre raro.
_PROHIBIDOS = frozenset('<>:"/|?*' + chr(92))


def _limpiar_nombre(texto: str) -> str:
    return "".join(c for c in texto if c not in _PROHIBIDOS and ord(c) >= 32)


def _nombre_seguro(indice: int, nombre_invitado: str | None, public_id: str) -> str:
    """`012 - Martín Peña.jpg`. Con índice adelante para que no se pisen ni se
    reordenen al abrir la carpeta."""
    extension = public_id.rsplit(".", 1)[-1].lower()
    if extension not in EXTENSIONES_PERMITIDAS:
        extension = "jpg"
    limpio = _limpiar_nombre((nombre_invitado or "").strip())[:60].strip()
    return f"{indice:03d} - {limpio}.{extension}" if limpio else f"{indice:03d}.{extension}"


def armar_zip(fotos: list[tuple[str | None, str]]):
    """Genera el ZIP de a pedazos. Recibe [(nombre_invitado, url), ...].

    Se usa ZIP_STORED, sin comprimir: los JPEG ya vienen comprimidos y volver a
    pasarlos por deflate gasta CPU para no bajar ni un uno por ciento.

    Una foto que no se puede descargar se saltea. Con doscientas fotos, que una
    URL falle no puede tirar abajo la descarga entera.
    """
    import httpx  # local: sólo hace falta para esto

    chorro = _Chorro()
    with zipfile.ZipFile(chorro, "w", zipfile.ZIP_STORED) as z:
        with httpx.Client(timeout=30.0, follow_redirects=True) as cliente:
            for indice, (nombre_invitado, url) in enumerate(fotos, start=1):
                try:
                    with cliente.stream("GET", url) as respuesta:
                        if respuesta.status_code != 200:
                            continue
                        interno = _nombre_seguro(indice, nombre_invitado, url)
                        with z.open(interno, "w") as destino:
                            for pedazo in respuesta.iter_bytes(64 * 1024):
                                destino.write(pedazo)
                                salida = chorro.tomar()
                                if salida:
                                    yield salida
                except httpx.HTTPError:
                    continue
                salida = chorro.tomar()
                if salida:
                    yield salida
    resto = chorro.tomar()
    if resto:
        yield resto


def nombre_del_archivo(nombre_evento: str, fecha) -> str:
    """El archivo se nombra con el evento y la fecha, no con un identificador."""
    limpio = _limpiar_nombre(nombre_evento).strip() or "evento"
    return f"{limpio} - {fecha.isoformat()}.zip"
