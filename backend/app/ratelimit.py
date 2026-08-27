"""Límite de pedidos en memoria, por IP y evento.

El contrato pide 30 pedidos cada 10 minutos sobre el endpoint de firma.

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

import threading
import time
from collections import deque

VENTANA_SEGUNDOS = 600
MAXIMO_PEDIDOS = 30

_pedidos: dict[tuple[str, str], deque[float]] = {}
_candado = threading.Lock()


def permitido(ip: str, codigo_publico: str, ahora: float | None = None) -> bool:
    """Registra el pedido y dice si entra dentro del límite."""
    momento = time.monotonic() if ahora is None else ahora
    clave = (ip, codigo_publico)
    with _candado:
        marcas = _pedidos.setdefault(clave, deque())
        limite_viejo = momento - VENTANA_SEGUNDOS
        while marcas and marcas[0] <= limite_viejo:
            marcas.popleft()
        if len(marcas) >= MAXIMO_PEDIDOS:
            return False
        marcas.append(momento)
        return True


def limpiar_vencidos(ahora: float | None = None) -> int:
    """Saca las claves sin pedidos recientes. Sin esto el diccionario sólo crece.

    Lo llama el endpoint de firma cada tanto: no hace falta una tarea de fondo
    para un diccionario que en un evento real tiene unos cientos de claves.
    """
    momento = time.monotonic() if ahora is None else ahora
    limite_viejo = momento - VENTANA_SEGUNDOS
    with _candado:
        vacias = [k for k, v in _pedidos.items() if not v or v[-1] <= limite_viejo]
        for k in vacias:
            del _pedidos[k]
        return len(vacias)


def reiniciar() -> None:
    """Sólo para las pruebas."""
    with _candado:
        _pedidos.clear()
