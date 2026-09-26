"""alembic/env.py con una DATABASE_URL que lleva "%".

Si la contraseña de Supabase tiene @ : / # ? o %, va codificada en la URL
(%40, %23...). env.py carga la URL en la configuración de Alembic, que pasa por
la interpolación de configparser: sin duplicar el "%", `alembic upgrade head`
corta con un ValueError. En Render el arranque es
`alembic upgrade head && uvicorn ...`, así que la API no llegaría a levantar.

Sin alembic.ini, como en test_esquema.py: su sección de logging reconfiguraría
los loggers de todo el proceso y las pruebas que miran el log dejarían de ver
sus mensajes.
"""

from __future__ import annotations

import io
from pathlib import Path

from alembic import command
from alembic.config import Config as ConfigAlembic
from sqlalchemy.engine import make_url

from app.config import obtener_config
from tests.conftest import URL_PRUEBA, sin_base

BACKEND = Path(__file__).resolve().parents[1]

# Como la del pooler de Supabase, con una contraseña que lleva @, # y %.
URL_CON_PORCIENTOS = (
    "postgresql+psycopg://postgres.abcdef:cl%40ve%23con%25raros"
    "@aws-0-sa-east-1.pooler.supabase.com:5432/postgres"
)


def config_alembic() -> ConfigAlembic:
    config = ConfigAlembic()
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    config.output_buffer = io.StringIO()
    return config


def test_una_url_con_porcientos_no_rompe_las_migraciones(monkeypatch):
    monkeypatch.setattr(obtener_config(), "DATABASE_URL", URL_CON_PORCIENTOS)
    config = config_alembic()
    command.upgrade(config, "head", sql=True)  # offline: no se conecta a ningún lado
    assert "recuperaciones_contrasena" in config.output_buffer.getvalue(), "llegó a la última"
    # El modo offline lee get_main_option; el online, get_section (engine_from_config).
    # Los dos tienen que ver la URL original, sin los "%%" del escape.
    assert config.get_main_option("sqlalchemy.url") == URL_CON_PORCIENTOS
    assert config.get_section(config.config_ini_section)["sqlalchemy.url"] == URL_CON_PORCIENTOS
    assert make_url(URL_CON_PORCIENTOS).password == "cl@ve#con%raros"


def test_una_url_sin_porcientos_queda_igual(monkeypatch):
    url = "postgresql+psycopg://transmiti:transmiti@localhost:5432/transmiti"
    monkeypatch.setattr(obtener_config(), "DATABASE_URL", url)
    config = config_alembic()
    command.upgrade(config, "head", sql=True)
    assert config.get_main_option("sqlalchemy.url") == url


@sin_base
def test_en_linea_se_conecta_con_una_url_con_porcientos(monkeypatch):
    """Contra la base de pruebas, con un parámetro codificado en la URL.
    `current` sólo lee la versión: no cambia nada."""
    separador = "&" if "?" in URL_PRUEBA else "?"
    url = f"{URL_PRUEBA}{separador}application_name=alembic%20con%20porcientos"
    monkeypatch.setattr(obtener_config(), "DATABASE_URL", url)
    config = config_alembic()
    command.current(config)
    assert config.get_section(config.config_ini_section)["sqlalchemy.url"] == url
