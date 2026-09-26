"""Límite de pedidos en memoria.

Cada cuenta de pedidos tiene una clave (una tupla de textos), un tope y una
ventana. Los usos, cada uno con sus números:

- La firma de subida lleva dos cuentas a la vez (ver routers/publico.py): una
  por celular, `(ip, evento, dispositivo_hash)`, y otra más alta por conexión,
  `(ip, evento)`. En un salón todos los invitados salen por la misma IP del
  wifi: con una sola cuenta por IP se bloqueaba a todos juntos.
- El registro de una foto lleva el mismo par de cuentas que la firma, aparte.
- El canje de pantalla, 30 cada 10 minutos por IP.
- El registro de cuentas, más estricto (ver routers/cuentas.py).
- El login, por IP y por email (ver routers/admin.py).

La IP sale de `ip_del_pedido`, una sola función para todos: de la IP depende
que cualquiera de estos topes sirva de algo.

Es en memoria a propósito: no hay Redis en el stack y agregarlo rompería la
regla 10. Tiene dos consecuencias que conviene tener presentes y que no son
graves para este caso de uso:

- Se reinicia cuando se reinicia el servicio. En Render gratuito, que duerme,
  pasa seguido.
- Si algún día hay más de una instancia, cada una lleva su propia cuenta y el
  límite efectivo se multiplica por la cantidad de instancias.

Sirve para frenar un script que golpea el endpoint, que es para lo que está.
No es una defensa contra un ataque distribuido.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from collections.abc import Sequence

from starlette.requests import Request

VENTANA_SEGUNDOS = 600
MAXIMO_PEDIDOS = 30

Clave = tuple[str, ...]

_pedidos: dict[Clave, deque[float]] = {}
# La ventana de cada clave. Hace falta para limpiar: una clave con ventana de
# una hora no se puede dar por vencida a los diez minutos, o el límite se
# reinicia solo.
_ventanas: dict[Clave, float] = {}
_candado = threading.Lock()

# Cada cuánto se barren las claves vencidas (ver `limpiar_cada_tanto`).
LIMPIEZA_CADA_SEGUNDOS = 60
_ultima_limpieza: float | None = None

# Cloudflare, que está delante de Render, escribe acá la IP que se le conectó y
# pisa la que haya mandado el cliente. Render agrega un valor al final de
# X-Forwarded-For pero no limpia los que llegan (feedback.render.com, "Send the
# correct X_FORWARDED_FOR"). Si algún día el servicio deja de estar detrás de
# Cloudflare, esta cabecera la podría escribir cualquiera: hay que revisarla.
CABECERA_IP_CONFIABLE = "cf-connecting-ip"

# El de uvicorn, que en Render ya sale en el log a nivel INFO.
_log = logging.getLogger("uvicorn.error")
_cabeceras_informadas = False


def _informar_cabeceras(request: Request) -> None:
    """Una vez por proceso, qué cabeceras de IP llegan. Sin los valores: sólo
    si están y cuántos saltos trae X-Forwarded-For. Alcanza para confirmar en el
    log de Render que `ip_del_pedido` decide con lo que corresponde."""
    global _cabeceras_informadas
    if _cabeceras_informadas:
        return
    _cabeceras_informadas = True
    reenviada = request.headers.get("x-forwarded-for") or ""
    _log.info(
        "ip_del_pedido: %s=%s, true-client-ip=%s, x-forwarded-for con %d valores",
        CABECERA_IP_CONFIABLE,
        "sí" if request.headers.get(CABECERA_IP_CONFIABLE) else "no",
        "sí" if request.headers.get("true-client-ip") else "no",
        len([v for v in reenviada.split(",") if v.strip()]),
    )


def ip_del_pedido(request: Request) -> str:
    """La IP con la que se cuentan los topes. La usan todos los endpoints.

    NUNCA el primer valor de X-Forwarded-For: ése lo escribe quien manda el
    pedido. Con uno inventado por pedido se evadía cualquier tope (el canje de
    6 dígitos se podía probar por fuerza bruta). En orden:

    1. `cf-connecting-ip`, que pone Cloudflare y el cliente no controla.
    2. El ÚLTIMO valor de X-Forwarded-For: lo agrega el proxy que tenemos
       adelante con la IP que se le conectó. Los anteriores son del cliente.
    3. `request.client.host`, sin proxy de por medio (desarrollo, pruebas).

    Antes de tocar esto en producción, conviene confirmar en Render qué
    cabeceras llegan: el primer pedido de cada arranque deja una línea en el
    log (`_informar_cabeceras`). Mandar uno con `X-Forwarded-For: 1.2.3.4` y
    mirar que diga `cf-connecting-ip=sí` y más de un valor en X-Forwarded-For
    (el inventado y los que agregan los proxies). Si dice `no`, esta función
    está usando el último valor de X-Forwarded-For: revisar cuál es.
    """
    _informar_cabeceras(request)
    confiable = (request.headers.get(CABECERA_IP_CONFIABLE) or "").strip()
    if confiable:
        return confiable
    reenviada = request.headers.get("x-forwarded-for")
    if reenviada:
        valores = [v.strip() for v in reenviada.split(",") if v.strip()]
        if valores:
            return valores[-1]
    return request.client.host if request.client else "desconocida"


def permitido(
    ip: str,
    codigo_publico: str,
    ahora: float | None = None,
    maximo: int = MAXIMO_PEDIDOS,
    ventana: float = VENTANA_SEGUNDOS,
) -> bool:
    """Registra el pedido en la cuenta `(ip, codigo_publico)` y dice si entra.

    `codigo_publico` es la segunda mitad de la clave. Los usos que no son de un
    evento pasan un nombre que no puede ser un código (los códigos miden 8
    caracteres y no llevan barras), así nunca comparten cuenta con uno.
    """
    return permitido_en_todas([((ip, codigo_publico), maximo)], ahora=ahora, ventana=ventana)


def permitido_en_todas(
    cuentas: Sequence[tuple[Clave, int]],
    ahora: float | None = None,
    ventana: float = VENTANA_SEGUNDOS,
) -> bool:
    """Registra el pedido en todas las cuentas, o en ninguna.

    `cuentas` es una lista de `(clave, tope)`. El pedido entra sólo si hay
    lugar en todas; si alguna lo frena, no se anota en ninguna. Así un celular
    que insiste después de su tope no le come lugar a la conexión que comparte
    con el resto del salón, y una conexión llena no le gasta la cuota a un
    celular que no llegó a pedir nada.

    Claves de distinto largo nunca se pisan: `(ip, evento)` y
    `(ip, evento, dispositivo)` son cuentas distintas aunque empiecen igual.

    Un pedido frenado no crea claves: si no, un script que inventa un
    dispositivo por pedido contra una conexión llena haría crecer el
    diccionario con cuentas vacías hasta la próxima limpieza.
    """
    momento = time.monotonic() if ahora is None else ahora
    limite_viejo = momento - ventana
    with _candado:
        for clave, maximo in cuentas:
            marcas = _pedidos.get(clave)
            while marcas and marcas[0] <= limite_viejo:
                marcas.popleft()
            if len(marcas or ()) >= maximo:
                return False
        for clave, _ in cuentas:
            _pedidos.setdefault(clave, deque()).append(momento)
            _ventanas[clave] = ventana
        return True


def limpiar_vencidos(ahora: float | None = None) -> int:
    """Saca las claves sin pedidos recientes. Sin esto el diccionario sólo crece.

    Los endpoints no la llaman directo sino por `limpiar_cada_tanto`: no hace
    falta una tarea de fondo para un diccionario que en un evento real tiene
    unos cientos de claves (una por celular y por conexión).
    """
    momento = time.monotonic() if ahora is None else ahora
    with _candado:
        vacias = [
            k
            for k, v in _pedidos.items()
            if not v or v[-1] <= momento - _ventanas.get(k, VENTANA_SEGUNDOS)
        ]
        for k in vacias:
            del _pedidos[k]
            _ventanas.pop(k, None)
        return len(vacias)


def limpiar_cada_tanto(ahora: float | None = None) -> int:
    """Lo que llaman los endpoints después de contar un pedido.

    `limpiar_vencidos` recorre el diccionario entero. Hacerlo en cada pedido
    convierte cada firma en un barrido de todas las claves: con esto se barre
    como mucho una vez por minuto, y un pedido común no paga nada.
    """
    global _ultima_limpieza
    momento = time.monotonic() if ahora is None else ahora
    with _candado:
        if _ultima_limpieza is not None and momento - _ultima_limpieza < LIMPIEZA_CADA_SEGUNDOS:
            return 0
        _ultima_limpieza = momento
    return limpiar_vencidos(momento)


def reiniciar() -> None:
    """Sólo para las pruebas."""
    global _ultima_limpieza
    with _candado:
        _pedidos.clear()
        _ventanas.clear()
        _ultima_limpieza = None
