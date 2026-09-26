"""Brevo y Cloudinary de mentira, y un pedido ASGI que mide cuándo sale la respuesta.

No es un módulo de pruebas (no empieza con `test_`): lo importan
test_recuperacion.py y test_mi_cuenta.py. Ningún pedido sale de verdad: los
fixtures de esos archivos reemplazan `httpx.post` y `httpx.delete` por estos.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass

import httpx

from app import email as correo

CLAVE_BREVO = "xkeysib-clave-de-prueba"
REMITENTE = "no-responder@transmitifoto.test"
URL_PANEL = "https://panel.transmitifoto.test"

_TOKEN_EN_EL_LINK = re.compile(r"/admin/restablecer#token=([A-Za-z0-9_-]+)")


class BrevoFalso:
    """Responde 201 como Brevo y guarda cada envío. `respuesta` puede devolver
    otra respuesta o una excepción; `demora` simula un Brevo lento."""

    def __init__(self) -> None:
        self.envios: list[dict] = []
        self.demora = 0.0
        self.respuesta = lambda: httpx.Response(201, json={"messageId": "<1@smtp-relay.brevo.com>"})

    def post(self, url, *, headers=None, json=None, timeout=None, **_):
        if url != correo.URL_BREVO:
            raise AssertionError(f"una prueba intentó un POST de verdad a {url}")
        if self.demora:
            time.sleep(self.demora)
        self.envios.append({"url": url, "headers": dict(headers or {}), "json": json,
                            "timeout": timeout})
        resultado = self.respuesta()
        if isinstance(resultado, Exception):
            raise resultado
        return resultado

    def token(self, indice: int = -1) -> str:
        """El token del link de un envío, sacado del texto del email."""
        encontrado = _TOKEN_EN_EL_LINK.search(self.envios[indice]["json"]["textContent"])
        assert encontrado, self.envios[indice]["json"]["textContent"]
        return encontrado.group(1)


class NubeFalsa:
    """El DELETE de la Admin API de Cloudinary: guarda cada pedido y responde
    como si hubiera borrado. `falla` puede devolver una respuesta o una
    excepción para simular errores."""

    def __init__(self) -> None:
        self.pedidos: list[dict] = []
        self.falla = None

    def delete(self, url, *, params=None, auth=None, timeout=None, **_):
        self.pedidos.append({"url": url, "params": dict(params or {}), "auth": auth})
        if self.falla is not None:
            resultado = self.falla()
            if isinstance(resultado, Exception):
                raise resultado
            return resultado
        if "public_ids[]" in (params or {}):
            return httpx.Response(200, json={"deleted": {params["public_ids[]"]: "deleted"}})
        return httpx.Response(200, json={"deleted": {"x": "deleted"}, "partial": False})

    def borrados(self) -> list[tuple[str, str]]:
        """[("imagen", public_id) | ("prefijo", prefijo)] en orden."""
        salida = []
        for p in self.pedidos:
            if "public_ids[]" in p["params"]:
                salida.append(("imagen", p["params"]["public_ids[]"]))
            else:
                salida.append(("prefijo", p["params"]["prefix"]))
        return salida


def prohibido(*_a, **_k):
    raise AssertionError("una prueba intentó un pedido de verdad a Cloudinary")


# ─────────────────────────────────────────────────────────────
# Un pedido ASGI directo, para medir cuándo sale la respuesta
# ─────────────────────────────────────────────────────────────

@dataclass
class Medicion:
    status: int
    cuerpo: bytes
    respuesta_s: float  # desde el pedido hasta que salió el último byte de la respuesta
    total_s: float      # desde el pedido hasta que terminó todo, tareas de fondo incluidas


def pedir_directo(app, metodo: str, ruta: str, cuerpo: dict, ip: str = "203.0.113.50") -> Medicion:
    """Llama a la app ASGI sin TestClient. El TestClient devuelve la respuesta
    recién cuando termina TODO, tareas de fondo incluidas, así que con él no se
    puede ver que la respuesta sale antes que el email. Acá sí: se anota el
    momento en que la app manda el último pedazo de la respuesta."""
    datos = json.dumps(cuerpo).encode()

    async def correr() -> Medicion:
        terminada = asyncio.Event()
        leido = False
        partes: list[bytes] = []
        estado = {"status": 0, "respuesta": None}

        async def recibir():
            nonlocal leido
            if not leido:
                leido = True
                return {"type": "http.request", "body": datos, "more_body": False}
            await terminada.wait()
            return {"type": "http.disconnect"}

        async def mandar(mensaje):
            if mensaje["type"] == "http.response.start":
                estado["status"] = mensaje["status"]
            elif mensaje["type"] == "http.response.body":
                partes.append(mensaje.get("body", b""))
                if not mensaje.get("more_body", False):
                    estado["respuesta"] = time.perf_counter() - inicio
                    terminada.set()

        alcance = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": metodo,
            "scheme": "http",
            "path": ruta,
            "raw_path": ruta.encode(),
            "root_path": "",
            "query_string": b"",
            "headers": [
                (b"host", b"testserver"),
                (b"content-type", b"application/json"),
                (b"content-length", str(len(datos)).encode()),
                (b"x-forwarded-for", ip.encode()),
            ],
            "client": ("127.0.0.1", 50000),
            "server": ("testserver", 80),
        }
        inicio = time.perf_counter()
        await app(alcance, recibir, mandar)
        total = time.perf_counter() - inicio
        terminada.set()
        return Medicion(estado["status"], b"".join(partes), estado["respuesta"], total)

    return asyncio.run(correr())
