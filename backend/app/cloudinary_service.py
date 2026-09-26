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


# Va adentro del ZIP cuando faltan fotos. "000" adelante para que quede primero
# al abrir la carpeta, antes que "001 - …jpg": es lo primero que hay que leer.
NOMBRE_FALTANTES = "000 - FALTAN FOTOS.txt"


def texto_faltantes(faltan: list[str], incompletas: list[str], total: int) -> str:
    """Lo que dice el archivo de faltantes. Lo lee quien organiza, en el
    celular o en la compu: sin palabras del sistema."""
    cuantas = len(faltan) + len(incompletas)
    if total == 1:
        titulo = "No se pudo bajar la foto."
    elif cuantas == total:
        titulo = f"No se pudo bajar ninguna de las {total} fotos."
    elif cuantas == 1:
        titulo = f"No se pudo bajar 1 de las {total} fotos."
    else:
        titulo = f"No se pudieron bajar {cuantas} de las {total} fotos."
    lineas = [titulo, "Probá descargar de nuevo en un rato."]
    if faltan:
        lineas += ["", "No están en este archivo:", *faltan]
    if incompletas:
        lineas += ["", "Están, pero quedaron cortadas:", *incompletas]
    return "\n".join(lineas) + "\n"


def armar_zip(fotos: list[tuple[str | None, str]]):
    """Genera el ZIP de a pedazos. Recibe [(nombre_invitado, url), ...].

    Se usa ZIP_STORED, sin comprimir: los JPEG ya vienen comprimidos y volver a
    pasarlos por deflate gasta CPU para no bajar ni un uno por ciento.

    Una foto que no se puede descargar se saltea. Con doscientas fotos, que una
    URL falle no puede tirar abajo la descarga entera. Pero no en silencio: la
    respuesta ya salió con 200 (es streaming), así que lo único que puede avisar
    que el ZIP está incompleto es el ZIP mismo. Si faltó alguna, al final va
    NOMBRE_FALTANTES con cuántas y cuáles; sin eso, un ZIP con 150 de 200 fotos
    (o con ninguna) se ve igual que uno completo, y quien lo baja cree que tiene
    todo justo antes de que se borren de Cloudinary.
    """
    import httpx  # local: sólo hace falta para esto

    faltan: list[str] = []
    incompletas: list[str] = []
    chorro = _Chorro()
    with zipfile.ZipFile(chorro, "w", zipfile.ZIP_STORED) as z:
        with httpx.Client(timeout=30.0, follow_redirects=True) as cliente:
            for indice, (nombre_invitado, url) in enumerate(fotos, start=1):
                interno = _nombre_seguro(indice, nombre_invitado, url)
                empezada = False
                try:
                    with cliente.stream("GET", url) as respuesta:
                        if respuesta.status_code != 200:
                            faltan.append(interno)
                            continue
                        with z.open(interno, "w") as destino:
                            empezada = True
                            for pedazo in respuesta.iter_bytes(64 * 1024):
                                destino.write(pedazo)
                                salida = chorro.tomar()
                                if salida:
                                    yield salida
                except httpx.HTTPError:
                    # Si la red se cortó a mitad de una foto, la entrada ya está
                    # en el ZIP con lo que llegó: está, pero cortada.
                    (incompletas if empezada else faltan).append(interno)
                    continue
                salida = chorro.tomar()
                if salida:
                    yield salida
        if faltan or incompletas:
            z.writestr(NOMBRE_FALTANTES, texto_faltantes(faltan, incompletas, len(fotos)))
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


# ─────────────────────────────────────────────────────────────
# Borrado de los archivos de un evento (lo usa app/limpieza.py)
# ─────────────────────────────────────────────────────────────

# Las fotos son `image` y los videos del evento, `video`. Los dos viven en la
# carpeta del evento, así que el mismo prefijo alcanza a todo lo que subió.
TIPOS_A_BORRAR = ("image", "video")

# Cloudinary borra por prefijo hasta mil archivos por pedido y avisa con
# `next_cursor` o `partial` que quedan más. Cien vueltas son cien mil archivos:
# si no alcanzan, algo raro pasa y es preferible cortar y reintentar en la
# próxima pasada que quedarse dando vueltas para siempre.
MAXIMO_VUELTAS_BORRADO = 100

_CODIGO_SEGURO = re.compile(r"[A-Za-z0-9_-]+")


class ErrorBorrado(Exception):
    """Cloudinary no contestó o contestó con error. El evento no se marca y la
    próxima pasada de limpieza lo vuelve a intentar."""


def prefijo_del_evento(codigo_publico: str) -> str:
    """`eventos/{codigo_publico}/`, CON la barra final.

    Sin la barra, el prefijo del evento `ab12` es `eventos/ab12`, y Cloudinary
    borraría también todo lo de `eventos/ab123...`, que es otro evento. Por lo
    mismo se rechaza un código vacío o con caracteres raros: nunca se pide un
    borrado más ancho que la carpeta de un evento.
    """
    if not _CODIGO_SEGURO.fullmatch(codigo_publico or ""):
        raise ErrorBorrado("código público inválido: no se pide ningún borrado")
    return carpeta_del_evento(codigo_publico) + "/"


def borrar_por_prefijo(prefijo: str, tipo: str) -> int:
    """Borra de Cloudinary todo lo de `tipo` cuyo public_id empieza con `prefijo`.

    Es la Admin API (DELETE /resources/{tipo}/upload), con el secreto, así que
    sólo corre acá. `invalidate=true` le pide además a la CDN que deje de servir
    las copias que tenga guardadas. Devuelve cuántos archivos borró.

    Borrar lo que ya no está no es un error: Cloudinary responde 200 sin nada
    borrado. Por eso reintentar un evento a medio borrar es seguro.
    """
    import httpx

    url = f"{API_CLOUDINARY}/{config.CLOUDINARY_CLOUD_NAME}/resources/{tipo}/upload"
    borrados = 0
    cursor: str | None = None
    for _ in range(MAXIMO_VUELTAS_BORRADO):
        parametros = {"prefix": prefijo, "invalidate": "true"}
        if cursor:
            parametros["next_cursor"] = cursor
        try:
            respuesta = httpx.delete(
                url,
                params=parametros,
                auth=(config.CLOUDINARY_API_KEY, config.CLOUDINARY_API_SECRET),
                timeout=30.0,
            )
        except httpx.HTTPError as e:
            raise ErrorBorrado(f"sin respuesta de Cloudinary ({type(e).__name__})") from e
        if respuesta.status_code >= 400:
            raise ErrorBorrado(
                f"Cloudinary respondió {respuesta.status_code}: {respuesta.text[:300]}"
            )
        try:
            cuerpo = respuesta.json()
        except ValueError as e:
            raise ErrorBorrado("Cloudinary respondió algo que no es JSON") from e

        borrados += sum(1 for v in (cuerpo.get("deleted") or {}).values() if v == "deleted")
        cursor = cuerpo.get("next_cursor") or None
        if not cursor and not cuerpo.get("partial"):
            return borrados
    raise ErrorBorrado(f"quedaron archivos sin borrar después de {MAXIMO_VUELTAS_BORRADO} pedidos")


def borrar_archivos_del_evento(codigo_publico: str) -> int:
    """Todas las fotos (aprobadas, pendientes y rechazadas) y todos los videos
    del evento. Si falla cualquiera de los pedidos, levanta ErrorBorrado."""
    prefijo = prefijo_del_evento(codigo_publico)
    return sum(borrar_por_prefijo(prefijo, tipo) for tipo in TIPOS_A_BORRAR)
