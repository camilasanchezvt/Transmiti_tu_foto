"""Aplicación FastAPI: CORS, routers y el manejador de errores uniforme.

Todo error de la API —los de negocio, los de validación y los 404 de rutas que
no existen— sale con la misma forma (sección 5 de CONSTRUIR-APP.md):

    { "error": { "codigo": "EVENTO_CERRADO", "mensaje": "Este evento ya terminó" } }

FASE 1 — los routers responden datos fijos. No hay base ni Cloudinary todavía.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as ExcepcionHTTP

from .config import obtener_config
from .database import get_db
from .errores import Codigo, ErrorApp
from .routers import admin, pantalla, publico
from .schemas import Salud

config = obtener_config()

app = FastAPI(
    title="Transmití tu foto",
    version="0.1.0",
    description=(
        "Fotos de invitados por QR, moderadas y proyectadas en pantalla.\n\n"
        "**Fase 1: todas las respuestas son datos fijos.** El contrato ya es el "
        "definitivo, así que las tres interfaces se pueden construir contra esto."
    ),
    docs_url="/docs",
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.origenes_cors,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


# ─────────────────────────────────────────────────────────────
# Manejadores de error — los tres desembocan en la misma forma
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

app.include_router(publico.router)
app.include_router(pantalla.router)
app.include_router(admin.router)
app.include_router(admin.protegido)


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
