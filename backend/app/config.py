"""Configuración leída del entorno.

Los nombres son exactamente los de la sección 9 de CONSTRUIR-APP.md y de .env.example.
El CLOUDINARY_API_SECRET se lee acá y no sale nunca de este proceso (regla 2).
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Base de datos. En Supabase va la cadena del POOLER EN MODO SESIÓN:
    # la conexión directa resuelve por IPv6 y falla desde Render.
    DATABASE_URL: str = "postgresql+psycopg://transmiti:transmiti@localhost:5432/transmiti"

    CLOUDINARY_CLOUD_NAME: str = ""
    CLOUDINARY_API_KEY: str = ""
    CLOUDINARY_API_SECRET: str = ""

    JWT_SECRET: str = "cambiame-en-produccion"
    JWT_HORAS: int = 12

    CORS_ORIGINS: str = "http://localhost:5173"
    ENTORNO: str = "desarrollo"

    @property
    def origenes_cors(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def es_produccion(self) -> bool:
        return self.ENTORNO.lower() == "produccion"


@lru_cache
def obtener_config() -> Config:
    return Config()
