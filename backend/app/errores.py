"""Errores de la aplicación y sus códigos.

Todo error de la API sale con la misma forma (sección 5 de CONSTRUIR-APP.md):

    { "error": { "codigo": "EVENTO_CERRADO", "mensaje": "Este evento ya terminó" } }

Los mensajes están escritos para que se puedan mostrar tal cual al invitado:
en segunda persona, cortos y sin palabras del sistema.
"""

from __future__ import annotations


class Codigo:
    """Los diez códigos del contrato. No inventar otros sin actualizar la sección 5."""

    EVENTO_NO_ENCONTRADO = "EVENTO_NO_ENCONTRADO"
    EVENTO_CERRADO = "EVENTO_CERRADO"
    EVENTO_BORRADOR = "EVENTO_BORRADOR"
    FOTO_NO_ENCONTRADA = "FOTO_NO_ENCONTRADA"
    ARCHIVO_INVALIDO = "ARCHIVO_INVALIDO"
    PUBLIC_ID_AJENO = "PUBLIC_ID_AJENO"
    LIMITE_ALCANZADO = "LIMITE_ALCANZADO"
    DEMASIADOS_PEDIDOS = "DEMASIADOS_PEDIDOS"
    NO_AUTORIZADO = "NO_AUTORIZADO"
    DATOS_INVALIDOS = "DATOS_INVALIDOS"


# Mensaje y estado HTTP por defecto de cada código.
_PREDETERMINADOS: dict[str, tuple[int, str]] = {
    Codigo.EVENTO_NO_ENCONTRADO: (404, "No encontramos este evento"),
    Codigo.EVENTO_CERRADO: (409, "Este evento ya terminó"),
    Codigo.EVENTO_BORRADOR: (404, "No encontramos este evento"),
    Codigo.FOTO_NO_ENCONTRADA: (404, "No encontramos esta foto"),
    Codigo.ARCHIVO_INVALIDO: (400, "Sólo podemos recibir fotos"),
    Codigo.PUBLIC_ID_AJENO: (403, "Esta foto no pertenece a este evento"),
    Codigo.LIMITE_ALCANZADO: (429, "Ya mandaste todas tus fotos. ¡Gracias!"),
    Codigo.DEMASIADOS_PEDIDOS: (429, "Esperá un momento y probá de nuevo"),
    Codigo.NO_AUTORIZADO: (401, "Necesitás iniciar sesión"),
    Codigo.DATOS_INVALIDOS: (422, "Los datos enviados no son válidos"),
}


class ErrorApp(Exception):
    """Error de negocio. El manejador de main.py lo convierte en la respuesta del contrato.

    Se usa siempre con un código del contrato:

        raise ErrorApp(Codigo.EVENTO_CERRADO)
        raise ErrorApp(Codigo.LIMITE_ALCANZADO, "Ya mandaste tus 10 fotos. ¡Gracias!")
    """

    def __init__(self, codigo: str, mensaje: str | None = None, http: int | None = None) -> None:
        predeterminado_http, predeterminado_mensaje = _PREDETERMINADOS.get(
            codigo, (400, "No pudimos procesar el pedido")
        )
        self.codigo = codigo
        self.mensaje = mensaje if mensaje is not None else predeterminado_mensaje
        self.http = http if http is not None else predeterminado_http
        super().__init__(f"{self.codigo}: {self.mensaje}")

    def como_respuesta(self) -> dict:
        return {"error": {"codigo": self.codigo, "mensaje": self.mensaje}}
