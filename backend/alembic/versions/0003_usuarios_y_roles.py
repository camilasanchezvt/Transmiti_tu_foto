"""Usuarios con rol y estado de cuenta: `administradores` pasa a `usuarios`.

Equivalente a la tabla `usuarios` y a `eventos.usuario_id` de db/schema.sql.

Hasta acá cada cuenta era un administrador que veía sólo sus eventos. Ahora
hay dos roles: `admin` ve y gestiona todo, `organizador` sólo lo suyo. Y las
cuentas se crean solas desde el registro público, así que nacen `pendiente` y
no pueden entrar hasta que un admin las habilite.

Las filas que ya existen quedan `admin` y `activa`. En producción hay una sola
cuenta, la de Camila, y tiene que seguir entrando y viendo todo después de
migrar. Por eso las dos columnas se agregan con un default provisorio que
completa las filas existentes, y recién después se pone el default de las
cuentas nuevas.

Los nombres de las restricciones y de la secuencia se renombran también, para
que una base migrada quede igual que una creada desde cero con schema.sql. Si
divergen, un error de restricción dice una cosa en local y otra en producción.

OJO con el downgrade: el esquema anterior no tiene estado de cuenta, así que al
volver atrás TODAS las cuentas pueden entrar otra vez, también las pendientes y
las dadas de baja, y cada una ve sólo sus eventos. Revisar las cuentas antes.

Revision ID: 0003_usuarios_y_roles
Revises: 0002_video_del_evento
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_usuarios_y_roles"
down_revision = "0002_video_del_evento"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.rename_table("administradores", "usuarios")
    op.execute("ALTER TABLE usuarios RENAME CONSTRAINT administradores_pkey TO usuarios_pkey")
    op.execute(
        "ALTER TABLE usuarios RENAME CONSTRAINT administradores_email_key TO usuarios_email_key"
    )
    op.execute("ALTER SEQUENCE administradores_id_seq RENAME TO usuarios_id_seq")

    # Default provisorio 'admin' / 'activa': es lo que completa las filas que ya
    # existen. Inmediatamente después pasa a ser el de una cuenta recién
    # registrada, que es organizador y espera que la habiliten.
    op.add_column(
        "usuarios",
        sa.Column("rol", sa.Text(), nullable=False, server_default=sa.text("'admin'")),
    )
    op.alter_column("usuarios", "rol", server_default=sa.text("'organizador'"))
    op.create_check_constraint(
        "usuarios_rol_check", "usuarios", "rol IN ('admin','organizador')"
    )

    op.add_column(
        "usuarios",
        sa.Column("estado", sa.Text(), nullable=False, server_default=sa.text("'activa'")),
    )
    op.alter_column("usuarios", "estado", server_default=sa.text("'pendiente'"))
    op.create_check_constraint(
        "usuarios_estado_check", "usuarios", "estado IN ('pendiente','activa','baja')"
    )

    # El dueño de un evento ya no es necesariamente un administrador.
    op.alter_column("eventos", "admin_id", new_column_name="usuario_id")
    op.execute(
        "ALTER TABLE eventos RENAME CONSTRAINT eventos_admin_id_fkey TO eventos_usuario_id_fkey"
    )
    # fotos.moderada_por sigue apuntando a la misma tabla: Postgres lleva la
    # clave foránea con el renombre, no hay nada que tocar.


def downgrade() -> None:
    op.execute(
        "ALTER TABLE eventos RENAME CONSTRAINT eventos_usuario_id_fkey TO eventos_admin_id_fkey"
    )
    op.alter_column("eventos", "usuario_id", new_column_name="admin_id")

    op.drop_constraint("usuarios_estado_check", "usuarios", type_="check")
    op.drop_column("usuarios", "estado")
    op.drop_constraint("usuarios_rol_check", "usuarios", type_="check")
    op.drop_column("usuarios", "rol")

    op.execute("ALTER SEQUENCE usuarios_id_seq RENAME TO administradores_id_seq")
    op.execute(
        "ALTER TABLE usuarios RENAME CONSTRAINT usuarios_email_key TO administradores_email_key"
    )
    op.execute("ALTER TABLE usuarios RENAME CONSTRAINT usuarios_pkey TO administradores_pkey")
    op.rename_table("usuarios", "administradores")
