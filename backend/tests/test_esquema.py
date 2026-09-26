"""db/schema.sql, los modelos y las migraciones describen la misma base.

Son tres fuentes de la misma verdad (models.py dice que "espejan db/schema.sql
exactamente"), y si divergen, un error de restricción dice una cosa en local y
otra en producción. Acá se construye la base de las tres maneras, cada una en
su propio esquema de Postgres, y se comparan columnas, tipos, DEFAULT,
restricciones (con sus nombres), índices y secuencias:

- `public`: la crea el fixture `motor_prueba` con los modelos (create_all).
- `esquema_sql`: db/schema.sql tal cual.
- `esquema_migrado`: el SQL offline de las migraciones, de la 0001 a la última
  (`alembic upgrade head --sql`), sin conectarse a ninguna base para generarlo.

Necesita Postgres. Los dos esquemas se crean y se borran en la misma prueba.
"""

from __future__ import annotations

import io
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config as ConfigAlembic

from tests.conftest import URL_PRUEBA, sin_base

pytestmark = sin_base

BACKEND = Path(__file__).resolve().parents[1]
SCHEMA_SQL = BACKEND.parent / "db" / "schema.sql"


def sql_de_las_migraciones() -> str:
    """El SQL de todas las migraciones, como lo imprime `alembic upgrade head --sql`.

    Sin alembic.ini a propósito: su sección de logging reconfiguraría los
    loggers de todo el proceso y las pruebas que miran el log dejarían de ver
    sus mensajes."""
    config = ConfigAlembic()
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    salida = io.StringIO()
    config.output_buffer = salida
    command.upgrade(config, "head", sql=True)
    return salida.getvalue()


def conectar() -> psycopg.Connection:
    return psycopg.connect(URL_PRUEBA.replace("postgresql+psycopg://", "postgresql://"),
                           autocommit=True)


def crear_esquema(conexion, nombre: str, sql: str) -> None:
    conexion.execute(f"DROP SCHEMA IF EXISTS {nombre} CASCADE")
    conexion.execute(f"CREATE SCHEMA {nombre}")
    conexion.execute(f"SET search_path TO {nombre}")
    try:
        conexion.execute(sql)
    finally:
        conexion.execute("SET search_path TO public")


def describir(conexion, esquema: str) -> dict[str, set]:
    """Todo lo que importa de un esquema, sin el nombre del esquema y sin la
    tabla de versiones de Alembic."""

    def filas(consulta: str) -> set[tuple]:
        return {
            tuple(str(v).replace(f"{esquema}.", "") if v is not None else None for v in fila)
            for fila in conexion.execute(consulta, {"esquema": esquema}).fetchall()
        }

    return {
        "columnas": filas("""
            SELECT table_name, column_name, data_type, is_nullable, column_default,
                   is_identity, identity_generation
            FROM information_schema.columns
            WHERE table_schema = %(esquema)s AND table_name <> 'alembic_version'
        """),
        "restricciones": filas("""
            SELECT rel.relname, con.conname, con.contype, pg_get_constraintdef(con.oid)
            FROM pg_constraint con
            JOIN pg_class rel ON rel.oid = con.conrelid
            JOIN pg_namespace esp ON esp.oid = rel.relnamespace
            WHERE esp.nspname = %(esquema)s AND rel.relname <> 'alembic_version'
        """),
        "indices": filas("""
            SELECT tablename, indexname, indexdef FROM pg_indexes
            WHERE schemaname = %(esquema)s AND tablename <> 'alembic_version'
        """),
        # Las de IDENTITY no figuran en information_schema.sequences.
        "secuencias": filas("""
            SELECT sec.relname FROM pg_class sec
            JOIN pg_namespace esp ON esp.oid = sec.relnamespace
            WHERE esp.nspname = %(esquema)s AND sec.relkind = 'S'
        """),
    }


def diferencias(a: dict[str, set], b: dict[str, set]) -> dict[str, tuple[list, list]]:
    return {
        clave: (sorted(a[clave] - b[clave], key=str), sorted(b[clave] - a[clave], key=str))
        for clave in a
        if a[clave] != b[clave]
    }


@pytest.fixture()
def esquemas(motor_prueba):
    """`public` (los modelos), `esquema_sql` y `esquema_migrado`, descriptos."""
    with conectar() as conexion:
        try:
            crear_esquema(conexion, "esquema_sql", SCHEMA_SQL.read_text(encoding="utf-8"))
            crear_esquema(conexion, "esquema_migrado", sql_de_las_migraciones())
            yield {nombre: describir(conexion, nombre)
                   for nombre in ("public", "esquema_sql", "esquema_migrado")}
        finally:
            conexion.execute("DROP SCHEMA IF EXISTS esquema_sql CASCADE")
            conexion.execute("DROP SCHEMA IF EXISTS esquema_migrado CASCADE")


def test_schema_sql_es_igual_a_los_modelos(esquemas):
    assert diferencias(esquemas["esquema_sql"], esquemas["public"]) == {}


def test_las_migraciones_llegan_al_mismo_esquema(esquemas):
    assert diferencias(esquemas["esquema_migrado"], esquemas["esquema_sql"]) == {}


def test_la_comparacion_mira_lo_nuevo(esquemas):
    """Que la comparación no pase por no mirar nada: lo de la migración 0006
    está en los tres esquemas."""
    for descripcion in esquemas.values():
        columnas = {(t, c) for t, c, *_ in descripcion["columnas"]}
        assert {("usuarios", "sesiones_desde"), ("usuarios", "tema"),
                ("usuarios", "pred_pantalla_qr"), ("eventos", "pantalla_fondo"),
                ("recuperaciones_contrasena", "token_hash")} <= columnas
        nombres = {n for _, n, *_ in descripcion["restricciones"]}
        assert {"usuarios_tema_check", "eventos_pantalla_transicion_check",
                "recuperaciones_contrasena_usuario_id_fkey",
                "recuperaciones_contrasena_token_hash_key"} <= nombres
        assert ("recuperaciones_contrasena_id_seq",) in descripcion["secuencias"]
        [cascada] = [d for _, n, _, d in descripcion["restricciones"]
                     if n == "recuperaciones_contrasena_usuario_id_fkey"]
        assert "ON DELETE CASCADE" in cascada
        assert "timestamp with time zone" in {
            tipo for t, c, tipo, *_ in descripcion["columnas"]
            if (t, c) == ("usuarios", "sesiones_desde")
        }, "regla 5: timestamptz"


def test_las_migraciones_se_pueden_generar_sin_base():
    """El SQL offline de la 0006 sale sin conectarse a nada."""
    sql = sql_de_las_migraciones()
    assert "0006_cuenta_y_recuperacion" in sql
    assert "CREATE TABLE recuperaciones_contrasena" in sql
    assert "timestamp without time zone" not in sql.lower()
