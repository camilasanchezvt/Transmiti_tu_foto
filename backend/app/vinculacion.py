"""Códigos cortos para vincular una pantalla sin tipear el token.

El problema que resuelve: el link de la pantalla mide 68 caracteres, de los
cuales 32 son el token al azar. Tipearlo con el control remoto de una tele, en
un teclado en pantalla y con la cruceta, es cinco minutos y un error de tipeo de
volver a empezar.

El panel genera un código de 6 dígitos y la tele lo canjea. Va en ese sentido y
no al revés porque un control remoto tiene teclado numérico: seis dígitos los
escribe bien, letras y símbolos no.

Sobre la seguridad del código corto:

- Dura 10 minutos y es de un solo uso.
- Hay un solo código activo por evento: generar uno nuevo invalida el anterior.
- El canje tiene límite de pedidos por IP (el mismo de ratelimit.py). Con 30
  intentos cada 10 minutos contra un millón de combinaciones, la probabilidad de
  acertar dentro de la ventana es de 0,003%.
- Lo peor que se consigue con un código robado es leer las fotos APROBADAS de un
  evento. No habilita a subir, ni a moderar, ni a ver las pendientes.

Vive en memoria, igual que ratelimit.py y por las mismas razones: no hay Redis
en el stack. Si el servicio se reinicia en el medio de una vinculación, hay que
generar el código de nuevo. Como la vinculación entera dura menos de un minuto y
Render sólo duerme el servicio tras un rato de inactividad, en la práctica no
molesta.
"""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass

VIGENCIA_SEGUNDOS = 600
LARGO_CODIGO = 6


@dataclass
class Vinculacion:
    codigo: str
    evento_id: int
    token_pantalla: str
    vence_en: float


_por_codigo: dict[str, Vinculacion] = {}
_candado = threading.Lock()


def _ahora() -> float:
    return time.monotonic()


def _limpiar(momento: float) -> None:
    """Saca los vencidos. Se llama con el candado tomado."""
    for codigo in [c for c, v in _por_codigo.items() if v.vence_en <= momento]:
        del _por_codigo[codigo]


def crear(evento_id: int, token_pantalla: str) -> tuple[str, int]:
    """Devuelve el código y cuántos segundos le quedan de vida.

    Si el evento ya tenía un código activo, queda invalidado: dos códigos vivos
    para la misma pantalla es una puerta abierta de más sin ninguna ventaja.
    """
    momento = _ahora()
    with _candado:
        _limpiar(momento)

        for codigo in [c for c, v in _por_codigo.items() if v.evento_id == evento_id]:
            del _por_codigo[codigo]

        # secrets y no random: es una credencial, aunque sea corta y efímera.
        for _ in range(50):
            codigo = f"{secrets.randbelow(10 ** LARGO_CODIGO):0{LARGO_CODIGO}d}"
            if codigo not in _por_codigo:
                _por_codigo[codigo] = Vinculacion(
                    codigo=codigo,
                    evento_id=evento_id,
                    token_pantalla=token_pantalla,
                    vence_en=momento + VIGENCIA_SEGUNDOS,
                )
                return codigo, VIGENCIA_SEGUNDOS
    raise RuntimeError("No se pudo generar un código libre")


def canjear(codigo: str) -> str | None:
    """Devuelve el token de pantalla y quema el código. None si no sirve."""
    limpio = "".join(c for c in codigo if c.isdigit())
    if len(limpio) != LARGO_CODIGO:
        return None

    momento = _ahora()
    with _candado:
        _limpiar(momento)
        vinculacion = _por_codigo.pop(limpio, None)
    return vinculacion.token_pantalla if vinculacion else None


def reiniciar() -> None:
    """Sólo para las pruebas."""
    with _candado:
        _por_codigo.clear()
