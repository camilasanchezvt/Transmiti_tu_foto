"""Esquemas de entrada y salida de la API (Pydantic v2).

Son el contrato de la sección 5 de CONSTRUIR-APP.md traducido a tipos. Estos
esquemas son DEFINITIVOS desde la Fase 1: las tres interfaces se construyen
contra ellos. No agregar, sacar ni renombrar campos sin actualizar la sección 5.

Regla 1: el `id` interno de un evento no aparece en ninguna respuesta pública.
Fijate que ni EventoPublico ni PantallaEvento lo tienen. Los esquemas de
administración sí, porque van detrás del Bearer.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EstadoEvento = Literal["borrador", "activo", "cerrado"]
EstadoFoto = Literal["pendiente", "aprobada", "rechazada"]


# ─────────────────────────────────────────────────────────────
# Error — la forma única de todos los errores del contrato
# ─────────────────────────────────────────────────────────────

class DetalleError(BaseModel):
    codigo: str = Field(examples=["EVENTO_CERRADO"])
    mensaje: str = Field(examples=["Este evento ya terminó"])


class RespuestaError(BaseModel):
    """{ "error": { "codigo": "...", "mensaje": "..." } }"""

    error: DetalleError


# ─────────────────────────────────────────────────────────────
# Públicos — los usa el celular del invitado
# ─────────────────────────────────────────────────────────────

class EventoPublico(BaseModel):
    """GET /api/e/{codigo_publico}

    Devuelve `estado` también cuando es `cerrado`, para que la app muestre la
    pantalla de cierre. Si es `borrador` el endpoint responde 404.
    """

    model_config = ConfigDict(json_schema_extra={"examples": [{
        "nombre": "Casamiento Ana y Juan",
        "fecha_evento": "2026-09-12",
        "estado": "activo",
        "max_fotos_por_dispositivo": 10,
    }]})

    nombre: str
    fecha_evento: date
    estado: EstadoEvento
    max_fotos_por_dispositivo: int


class PedidoFirma(BaseModel):
    """Cuerpo de POST /api/e/{codigo_publico}/firma"""

    dispositivo_hash: str = Field(min_length=8, max_length=128, examples=["9f2c1a7b4e8d0c35"])


class Firma(BaseModel):
    """Respuesta de POST /api/e/{codigo_publico}/firma

    Se firman sólo `folder` y `timestamp`. La carpeta es siempre
    `eventos/{codigo_publico}`. El api_secret nunca sale del backend.
    """

    cloud_name: str
    api_key: str
    timestamp: int
    signature: str
    folder: str = Field(examples=["eventos/ab12cd34"])


class FotoNueva(BaseModel):
    """Cuerpo de POST /api/e/{codigo_publico}/fotos

    El `public_id` tiene que empezar con `eventos/{codigo_publico}/`. Sin esa
    verificación cualquiera podría registrar la URL de una imagen ajena.
    """

    public_id: str = Field(examples=["eventos/ab12cd34/k3j2h1"])
    url: str = Field(examples=["https://res.cloudinary.com/demo/image/upload/v1/eventos/ab12cd34/k3j2h1.jpg"])
    ancho: int = Field(gt=0)
    alto: int = Field(gt=0)
    bytes: int = Field(gt=0)
    dispositivo_hash: str = Field(min_length=8, max_length=128)
    nombre_invitado: str | None = Field(default=None, max_length=80)


class FotoRegistrada(BaseModel):
    """Respuesta 201 de POST /api/e/{codigo_publico}/fotos"""

    id: int
    estado: EstadoFoto


# ─────────────────────────────────────────────────────────────
# Pantalla — la usa la notebook del proyector
# ─────────────────────────────────────────────────────────────

class PantallaEvento(BaseModel):
    nombre: str
    codigo_publico: str
    estado: EstadoEvento


class PantallaConfig(BaseModel):
    segundos_por_foto: int
    intervalo_polling_ms: int
    maximo_buffer: int


class Pantalla(BaseModel):
    """GET /api/pantalla/{token_pantalla}"""

    evento: PantallaEvento
    config: PantallaConfig


class FotoPantalla(BaseModel):
    """Una foto tal como la ve la pantalla. Sin estado: son todas aprobadas."""

    id: int
    url: str
    ancho: int | None
    alto: int | None
    nombre_invitado: str | None


class ColaPantalla(BaseModel):
    """GET /api/pantalla/{token_pantalla}/fotos

    `desde=0` devuelve las últimas `limite` aprobadas, de la más vieja a la más
    nueva (arranque en frío). `desde=N` devuelve las aprobadas con id > N,
    ascendente (polling normal).

    `ultimo_id` es el mayor id devuelto, o el `desde` recibido si no vino nada.
    """

    fotos: list[FotoPantalla]
    ultimo_id: int


# ─────────────────────────────────────────────────────────────
# Administración — detrás de Authorization: Bearer
# ─────────────────────────────────────────────────────────────

class PedidoLogin(BaseModel):
    email: str = Field(examples=["ana@transmitifoto.test"])
    password: str = Field(min_length=1)


class Sesion(BaseModel):
    token: str
    expira_en: datetime


class EventoNuevo(BaseModel):
    """Cuerpo de POST /api/admin/eventos. Nombre y fecha, nada más."""

    nombre: str = Field(min_length=1, max_length=120)
    fecha_evento: date


class CambioEstadoEvento(BaseModel):
    """Cuerpo de PATCH /api/admin/eventos/{id}"""

    estado: EstadoEvento


class EventoAdmin(BaseModel):
    """Un evento visto desde el panel: con sus dos claves y sus totales."""

    id: int
    nombre: str
    fecha_evento: date
    estado: EstadoEvento
    codigo_publico: str
    token_pantalla: str
    pendientes: int
    aprobadas: int
    rechazadas: int


class FotoAdmin(BaseModel):
    """Una foto vista desde la bandeja de moderación."""

    id: int
    url: str
    ancho: int | None
    alto: int | None
    bytes: int | None
    estado: EstadoFoto
    nombre_invitado: str | None
    subida_en: datetime


class ListaFotosAdmin(BaseModel):
    """GET /api/admin/eventos/{id}/fotos"""

    fotos: list[FotoAdmin]
    ultimo_id: int


class Resumen(BaseModel):
    """GET /api/admin/eventos/{id}/resumen"""

    pendientes: int
    aprobadas: int
    rechazadas: int


class CambioEstadoFoto(BaseModel):
    """Cuerpo de PATCH /api/admin/fotos/{id}. Moderar es idempotente."""

    estado: EstadoFoto


class FotoModerada(BaseModel):
    """Respuesta de PATCH /api/admin/fotos/{id}"""

    id: int
    estado: EstadoFoto


class LoteModeracion(BaseModel):
    """Cuerpo de POST /api/admin/fotos/lote"""

    ids: list[int] = Field(min_length=1, examples=[[128, 129, 130]])
    estado: EstadoFoto


class ResultadoLote(BaseModel):
    afectadas: int


# ─────────────────────────────────────────────────────────────
# Vinculación de pantalla por código corto
# ─────────────────────────────────────────────────────────────

class CodigoVinculacion(BaseModel):
    """Respuesta de POST /api/admin/eventos/{id}/vincular

    Existe porque el link de la pantalla mide 68 caracteres y hay que poder
    cargarlo con el control remoto de una tele.
    """

    codigo: str = Field(examples=["394812"])
    expira_en: datetime


class PedidoCanje(BaseModel):
    """Cuerpo de POST /api/pantalla/canjear. Se aceptan espacios y guiones."""

    codigo: str = Field(min_length=6, max_length=16, examples=["394 812"])


class TokenDePantalla(BaseModel):
    """Respuesta del canje. Es la única vez que el token viaja sin estar en la URL."""

    token_pantalla: str


# ─────────────────────────────────────────────────────────────
# Salud
# ─────────────────────────────────────────────────────────────

class Salud(BaseModel):
    """GET /api/salud — sin auth."""

    estado: str = Field(examples=["ok"])
    base: str = Field(examples=["ok"])
