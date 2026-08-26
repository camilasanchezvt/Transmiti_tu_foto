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

    # Este valor por defecto sólo sirve para desarrollo y está escrito en el
    # repositorio, así que es público. La validación de abajo impide arrancar
    # en producción con él.
    JWT_SECRET: str = "solo-para-desarrollo-no-usar-en-produccion"
    JWT_HORAS: int = 12

    CORS_ORIGINS: str = "http://localhost:5173"
    ENTORNO: str = "desarrollo"

    @property
    def origenes_cors(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def es_produccion(self) -> bool:
        return self.ENTORNO.lower() == "produccion"

    def model_post_init(self, _contexto: object) -> None:
        """Falla al arrancar, no en el primer login, si el despliegue está mal.

        Un JWT_SECRET débil o el de desarrollo permitirían firmar tokens de
        administrador a mano. Es preferible que Render no levante el servicio
        antes que servir un panel abierto.
        """
        if not self.es_produccion:
            return
        if self.JWT_SECRET == Config.model_fields["JWT_SECRET"].default:
            raise RuntimeError(
                "JWT_SECRET sigue siendo el de desarrollo, que es público. "
                "Generá uno con: python -c \"import secrets; print(secrets.token_urlsafe(48))\""
            )
        if len(self.JWT_SECRET) < 32:
            raise RuntimeError(
                f"JWT_SECRET tiene {len(self.JWT_SECRET)} caracteres; hacen falta 32 o más."
            )
        if not self.CLOUDINARY_API_SECRET:
            raise RuntimeError("Falta CLOUDINARY_API_SECRET: no se pueden firmar las subidas.")


@lru_cache
def obtener_config() -> Config:
    return Config()
