"""Aplicación FastAPI: CORS, routers y el manejador de errores uniforme.

Todo error de la API —los de negocio, los de validación y los 404 de rutas que
no existen— sale con la misma forma (sección 5 de CONSTRUIR-APP.md):

    { "error": { "codigo": "EVENTO_CERRADO", "mensaje": "Este evento ya terminó" } }

/docs dice lo mismo: el 422 de cada endpoint se documenta con RespuestaError
(ver `_RESPUESTAS_COMUNES`) y no con el {"detail": [...]} que FastAPI pone solo.

El lifespan arranca la limpieza de Cloudinary a los 30 días (app/limpieza.py)
en segundo plano, sólo en producción y con las credenciales cargadas.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import DataError, SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as ExcepcionHTTP

from . import limpieza
from .config import obtener_config
from .database import get_db
from .errores import Codigo, ErrorApp
from .routers import admin, cuentas, pantalla, publico
from .schemas import RespuestaError, Salud

config = obtener_config()


@asynccontextmanager
async def ciclo_de_vida(_app: FastAPI) -> AsyncIterator[None]:
    """La limpieza se agenda y el arranque sigue: la primera pasada espera
    ~60 s, así que ni el arranque ni el health check de Render la esperan.

    Apagada en desarrollo y en las pruebas (LIMPIEZA_ACTIVA, ver config.py) y
    siempre que falte el secreto de Cloudinary.

    Los dos mensajes empiezan con "limpieza:", como todos los del módulo: el
    log de uvicorn no muestra el nombre del logger, y en Render se busca por esa
    palabra para confirmar que quedó andando. Apagada en producción es una
    advertencia: las fotos quedarían en Cloudinary para siempre.
    """
    tarea: asyncio.Task[None] | None = None
    config_actual = obtener_config()
    if config_actual.limpieza_activa:
        tarea = asyncio.create_task(limpieza.bucle_de_limpieza())
        limpieza.log.info(
            "limpieza: activa, borra de Cloudinary a los %s días de la fecha de cada evento",
            limpieza.DIAS_HASTA_BORRAR,
        )
    elif config_actual.es_produccion:
        limpieza.log.warning(
            "limpieza: APAGADA, no se borra nada de Cloudinary "
            "(LIMPIEZA_ACTIVA=false o faltan credenciales de Cloudinary)"
        )
    try:
        yield
    finally:
        if tarea is not None:
            tarea.cancel()
            with suppress(asyncio.CancelledError):
                await tarea


app = FastAPI(
    title="Transmití tu foto",
    version="0.1.0",
    description=(
        "Fotos de invitados por QR, revisadas y proyectadas en pantalla.\n\n"
        "Todos los errores tienen la misma forma: "
        '`{"error": {"codigo": "...", "mensaje": "..."}}`. '
        "El contrato completo está en la sección 5 de CONSTRUIR-APP.md."
    ),
    docs_url="/docs",
    redoc_url=None,
    lifespan=ciclo_de_vida,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.origenes_cors,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


# ─────────────────────────────────────────────────────────────
# Manejadores de error — todos desembocan en la misma forma
# ─────────────────────────────────────────────────────────────

def _respuesta(codigo: str, mensaje: str, http: int) -> JSONResponse:
    return JSONResponse(
        status_code=http,
        content={"error": {"codigo": codigo, "mensaje": mensaje}},
    )


@app.exception_handler(ErrorApp)
async def manejar_error_app(_: Request, exc: ErrorApp) -> JSONResponse:
    return _respuesta(exc.codigo, exc.mensaje, exc.http)


@app.exception_handler(RequestValidationError)
async def manejar_validacion(_: Request, exc: RequestValidationError) -> JSONResponse:
    """Un cuerpo mal formado es DATOS_INVALIDOS, no el 422 crudo de FastAPI."""
    error = ErrorApp(Codigo.DATOS_INVALIDOS)
    return _respuesta(error.codigo, error.mensaje, error.http)


@app.exception_handler(DataError)
async def manejar_dato_fuera_de_rango(_: Request, exc: DataError) -> JSONResponse:
    """Un valor que Postgres no puede guardar ni comparar en su columna: casi
    siempre un id que no entra en bigint (/api/admin/eventos/100000000000000000000).
    Pydantic lo acepta porque en Python un int no tiene tope, y sin esto psycopg
    levanta DataError y sale un 500. Es un dato inválido del pedido, no una
    falla del servidor. La sesión la cierra get_db al salir."""
    error = ErrorApp(Codigo.DATOS_INVALIDOS)
    return _respuesta(error.codigo, error.mensaje, error.http)


@app.exception_handler(ExcepcionHTTP)
async def manejar_http(_: Request, exc: ExcepcionHTTP) -> JSONResponse:
    """Rutas inexistentes y métodos no permitidos también respetan el contrato."""
    if exc.status_code == 401:
        error = ErrorApp(Codigo.NO_AUTORIZADO)
        return _respuesta(error.codigo, error.mensaje, error.http)
    if exc.status_code == 404:
        return _respuesta("EVENTO_NO_ENCONTRADO", "No encontramos lo que buscabas", 404)
    return _respuesta("DATOS_INVALIDOS", str(exc.detail), exc.status_code)


# ─────────────────────────────────────────────────────────────
# Routers
# ─────────────────────────────────────────────────────────────

# Un 422 de validación sale como DATOS_INVALIDOS (manejar_validacion). Sin
# declararlo acá, FastAPI documenta en /docs su propio HTTPValidationError, con
# una forma que la API nunca devuelve. Va en cada router y no en FastAPI(...):
# así no le aparece un 422 a /api/salud, que no recibe nada.
_RESPUESTAS_COMUNES = {422: {"model": RespuestaError, "description": "DATOS_INVALIDOS"}}

for _router in (
    publico.router,
    pantalla.router,
    admin.router,
    admin.protegido,
    cuentas.publico,
    cuentas.administracion,
):
    app.include_router(_router, responses=_RESPUESTAS_COMUNES)


@app.get("/api/salud", response_model=Salud, tags=["salud"], summary="Health check")
def salud(db: Session = Depends(get_db)) -> Salud:
    """Sin auth. Render lo usa para saber si el servicio está vivo.

    Responde 200 aunque la base no conteste, con `base` en "caida". Si devolviera
    un error, Render reiniciaría el servicio en loop por un problema que no es
    del servicio: cuando Supabase gratuito se pausa, lo que hay que hacer es
    despertar Supabase, no reiniciar la API.
    """
    try:
        db.execute(text("SELECT 1"))
        estado_base = "ok"
    except SQLAlchemyError:
        estado_base = "caida"
    return Salud(estado="ok", base=estado_base)
