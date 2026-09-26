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

from .config import obtener_config
from .errores import Codigo, ErrorApp

config = obtener_config()

# Sólo imágenes. Nada de video.
EXTENSIONES_PERMITIDAS = ("jpg", "jpeg", "png", "webp", "heic")
TIPOS_PERMITIDOS = ("image/jpeg", "image/png", "image/webp", "image/heic")

HOST_CLOUDINARY = "res.cloudinary.com"

# Lo que va después de `eventos/{codigo}/` en un public_id.
_SUFIJO_VALIDO = re.compile(r"[A-Za-z0-9_-]{1,100}")


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
    # Ni vacío, ni con subcarpetas, ni saliendo de la carpeta por las suyas: el
    # sufijo que genera Cloudinary son letras y números. Con esto, además, el
    # public_id se puede meter tal cual en el patrón de verificar_url.
    if not _SUFIJO_VALIDO.fullmatch(resto):
        raise ErrorApp(Codigo.PUBLIC_ID_AJENO)


def verificar_url(url: str, public_id: str) -> None:
    """La URL tiene que ser EXACTAMENTE la de la imagen subida, sin agregados.

    El brief sólo pide verificar el public_id, pero el campo que después se
    proyecta es `url`. Por eso se exige la forma que devuelve Cloudinary al
    subir, y nada más:

        https://res.cloudinary.com/{cloud}/image/upload/v{version}/{public_id}.{ext}

    Antes alcanzaba con que `/image/upload/` y el public_id aparecieran en algún
    lugar de la ruta, y pasaban cosas como éstas:

    - `.../upload/l_fetch:.../eventos/X/a.jpg`: tapa la foto con una imagen de
      afuera. Lo mismo cualquier otra transformación.
    - `.../upload/d_eventos:otro:foto.jpg/eventos/X/noexiste.jpg`: muestra la
      imagen por defecto, que es de otro evento.
    - `.../upload/v1/eventos/X/a/../../../../otracuenta/image/upload/b.jpg`: el
      navegador resuelve los `..` y carga una imagen de OTRA cuenta de
      Cloudinary, que su dueño puede cambiar después de que la aprueben.

    Sin CLOUDINARY_CLOUD_NAME (desarrollo, pruebas) se acepta cualquier nombre
    de cuenta bien formado; en producción la configuración lo exige.
    """
    nube = re.escape(config.CLOUDINARY_CLOUD_NAME) if config.CLOUDINARY_CLOUD_NAME else r"[A-Za-z0-9_-]+"
    extensiones = "|".join(EXTENSIONES_PERMITIDAS)
    patron = (
        rf"https://{re.escape(HOST_CLOUDINARY)}/{nube}/image/upload/"
        rf"(?:v\d+/)?{re.escape(public_id)}\.(?i:{extensiones})"
    )
    if not re.fullmatch(patron, url):
        # /video/upload/ y /raw/upload/ quedan afuera: sólo imágenes.
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


# ─────────────────────────────────────────────────────────────
# Video del evento (create_slideshow, en beta en Cloudinary)
# ─────────────────────────────────────────────────────────────

API_CLOUDINARY = "https://api.cloudinary.com/v1_1"

# Cloudinary no publica un tope de diapositivas. 150 fotos a 3 s son 7 minutos
# y medio: más largo que eso ya no se mira entero.
MAX_FOTOS_VIDEO = 150
VIDEO_ANCHO, VIDEO_ALTO = 1280, 720
VIDEO_MS_POR_FOTO = 3000
VIDEO_MS_TRANSICION = 800


def elegir_fotos_para_video(public_ids: list[str], tope: int = MAX_FOTOS_VIDEO) -> list[str]:
    """Todas si entran. Si sobran, se eligen repartidas a lo largo de la noche,
    no las primeras: el video tiene que contar el evento de punta a punta."""
    if len(public_ids) <= tope:
        return list(public_ids)
    if tope == 1:
        return [public_ids[0]]
    ultimo = len(public_ids) - 1
    return [public_ids[round(i * ultimo / (tope - 1))] for i in range(tope)]


def manifiesto_video(public_ids: list[str]) -> str:
    """El manifest_json de create_slideshow. Los tiempos van en milisegundos
    salvo `du`, la duración total, que va en segundos."""
    import json

    duracion = max(1, round(len(public_ids) * VIDEO_MS_POR_FOTO / 1000))
    return json.dumps(
        {
            "w": VIDEO_ANCHO,
            "h": VIDEO_ALTO,
            "du": duracion,
            "vars": {
                "sdur": VIDEO_MS_POR_FOTO,
                "tdur": VIDEO_MS_TRANSICION,
                "slides": [{"media": f"i:{p}"} for p in public_ids],
            },
        },
        separators=(",", ":"),
    )


def _firmar_parametros(parametros: dict[str, str | int]) -> str:
    """Mismo algoritmo que `firmar`: orden alfabético, unidos por &, secreto al final."""
    a_firmar = "&".join(f"{k}={parametros[k]}" for k in sorted(parametros))
    return hashlib.sha1((a_firmar + config.CLOUDINARY_API_SECRET).encode("utf-8")).hexdigest()


def pedir_video(codigo_publico: str, public_ids: list[str], momento: int | None = None) -> str:
    """Le pide a Cloudinary que arme el video. Devuelve su public_id.

    Es asincrónico: Cloudinary responde "processing" enseguida y el MP4 aparece
    minutos después. `consultar_video` dice cuándo está.
    """
    import httpx

    timestamp = int(time.time()) if momento is None else momento
    parametros: dict[str, str | int] = {
        "manifest_json": manifiesto_video(public_ids),
        "public_id": f"{carpeta_del_evento(codigo_publico)}/video-{timestamp}",
        "timestamp": timestamp,
    }
    cuerpo = {
        **parametros,
        "signature": _firmar_parametros(parametros),
        "api_key": config.CLOUDINARY_API_KEY,
    }
    try:
        respuesta = httpx.post(
            f"{API_CLOUDINARY}/{config.CLOUDINARY_CLOUD_NAME}/video/create_slideshow",
            data=cuerpo,
            timeout=30.0,
        )
    except httpx.HTTPError as e:
        raise ErrorVideo(f"sin respuesta de Cloudinary: {e}") from e
    if respuesta.status_code >= 400:
        raise ErrorVideo(f"Cloudinary respondió {respuesta.status_code}: {respuesta.text[:500]}")
    return str(parametros["public_id"])


def consultar_video(public_id: str) -> str | None:
    """La URL del MP4 si ya está listo; None si todavía no existe.

    Usa la Admin API con el secreto, así que sólo corre acá. Un error de red se
    trata como "todavía no": el panel vuelve a preguntar en unos segundos.
    """
    import httpx

    try:
        respuesta = httpx.get(
            f"{API_CLOUDINARY}/{config.CLOUDINARY_CLOUD_NAME}/resources/video/upload/{public_id}",
            auth=(config.CLOUDINARY_API_KEY, config.CLOUDINARY_API_SECRET),
            timeout=15.0,
        )
    except httpx.HTTPError:
        return None
    if respuesta.status_code != 200:
        return None
    return respuesta.json().get("secure_url")


class ErrorVideo(Exception):
    """Cloudinary no aceptó el pedido. Va al log; el panel muestra `fallo`."""
