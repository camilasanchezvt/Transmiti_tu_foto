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

    # El borrado automático de Cloudinary a los 30 días (app/limpieza.py). Sin
    # definir, corre sólo en producción: en desarrollo no hay a quién borrarle
    # nada, y en las pruebas no puede salir ni un pedido de verdad. Con `true`
    # o `false` se fuerza. Aun forzado, sin las credenciales de Cloudinary no
    # arranca: sin el secreto no hay con qué pedir el borrado.
    LIMPIEZA_ACTIVA: bool | None = None

    # El email de "olvidé mi contraseña" sale por Brevo, por su API HTTP
    # (app/email.py). Las cuatro son opcionales: sin la clave o sin el
    # remitente la app arranca igual y la recuperación responde lo mismo, pero
    # no manda nada y lo avisa en el log. EMAIL_REMITENTE tiene que estar
    # verificado en Brevo (Senders); si no, Brevo rechaza el envío.
    BREVO_API_KEY: str = ""
    EMAIL_REMITENTE: str = ""
    EMAIL_REMITENTE_NOMBRE: str = "Transmití tu foto"
    # Dónde vive el panel, para armar el link del email. Sale de la
    # configuración y nunca del pedido: con la cabecera Host, cualquiera podría
    # hacer que el link con el token apunte a su propio sitio. Sin definir, el
    # primer origen https de CORS_ORIGINS (o el primero, en desarrollo).
    URL_PANEL: str = ""

    @property
    def origenes_cors(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def url_panel(self) -> str:
        """Sin la barra final: el link se arma como `{url_panel}/admin/restablecer`."""
        if self.URL_PANEL.strip():
            return self.URL_PANEL.strip().rstrip("/")
        origenes = self.origenes_cors
        seguros = [o for o in origenes if o.lower().startswith("https://")]
        elegido = (seguros or origenes or ["http://localhost:5173"])[0]
        return elegido.rstrip("/")

    @property
    def email_configurado(self) -> bool:
        return bool(self.BREVO_API_KEY.strip() and self.EMAIL_REMITENTE.strip())

    @property
    def es_produccion(self) -> bool:
        return self.ENTORNO.lower() == "produccion"

    @property
    def limpieza_activa(self) -> bool:
        pedida = self.es_produccion if self.LIMPIEZA_ACTIVA is None else self.LIMPIEZA_ACTIVA
        credenciales = (
            self.CLOUDINARY_CLOUD_NAME and self.CLOUDINARY_API_KEY and self.CLOUDINARY_API_SECRET
        )
        return bool(pedida and credenciales)

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
