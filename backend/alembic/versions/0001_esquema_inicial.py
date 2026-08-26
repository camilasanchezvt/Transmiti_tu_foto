"""Esquema inicial: administradores, eventos y fotos.

Equivalente a db/schema.sql. Escrita a mano y no autogenerada, para poder
garantizar esa equivalencia: db/schema.sql es lo que se aplica en local por
docker compose, y esta migración es lo que se aplica en Supabase. Si las dos
divergen, el sistema anda distinto en desarrollo y en producción.

Revision ID: 0001_esquema_inicial
Revises:
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001_esquema_inicial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "administradores",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("nombre", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column(
            "creado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )

    op.create_table(
        "eventos",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("admin_id", sa.BigInteger(), nullable=False),
        sa.Column("nombre", sa.Text(), nullable=False),
        sa.Column("fecha_evento", sa.Date(), nullable=False),
        sa.Column("codigo_publico", sa.Text(), nullable=False),
        sa.Column("token_pantalla", sa.Text(), nullable=False),
        sa.Column(
            "estado", sa.Text(), server_default=sa.text("'borrador'"), nullable=False
        ),
        sa.Column(
            "max_fotos_por_dispositivo",
            sa.Integer(),
            server_default=sa.text("10"),
            nullable=False,
        ),
        sa.Column(
            "segundos_por_foto", sa.Integer(), server_default=sa.text("7"), nullable=False
        ),
        sa.Column(
            "creado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("cerrado_en", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "estado IN ('borrador','activo','cerrado')", name="eventos_estado_check"
        ),
        sa.ForeignKeyConstraint(["admin_id"], ["administradores.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("codigo_publico"),
        sa.UniqueConstraint("token_pantalla"),
    )

    op.create_table(
        "fotos",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("evento_id", sa.BigInteger(), nullable=False),
        sa.Column("public_id", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("ancho", sa.Integer(), nullable=True),
        sa.Column("alto", sa.Integer(), nullable=True),
        sa.Column("bytes", sa.Integer(), nullable=True),
        sa.Column(
            "estado", sa.Text(), server_default=sa.text("'pendiente'"), nullable=False
        ),
        sa.Column("dispositivo_hash", sa.Text(), nullable=True),
        sa.Column("nombre_invitado", sa.Text(), nullable=True),
        sa.Column(
            "subida_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("moderada_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("moderada_por", sa.BigInteger(), nullable=True),
        sa.CheckConstraint(
            "estado IN ('pendiente','aprobada','rechazada')", name="fotos_estado_check"
        ),
        sa.ForeignKeyConstraint(["evento_id"], ["eventos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["moderada_por"], ["administradores.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
    )

    # El índice del polling de la pantalla. Sin este, a las 200 fotos se arrastra.
    op.create_index("idx_fotos_pantalla", "fotos", ["evento_id", "estado", "id"])

    # Índice parcial: sólo las pendientes. Es el que usa la bandeja de moderación.
    op.create_index(
        "idx_fotos_pendientes",
        "fotos",
        ["evento_id", "id"],
        postgresql_where=sa.text("estado = 'pendiente'"),
    )

    # Para el listado del panel, ordenado por lo más reciente.
    op.create_index("idx_fotos_recientes", "fotos", ["evento_id", sa.text("subida_en DESC")])

    # Para contar cuántas subió un dispositivo.
    op.create_index("idx_fotos_dispositivo", "fotos", ["evento_id", "dispositivo_hash"])


def downgrade() -> None:
    op.drop_index("idx_fotos_dispositivo", table_name="fotos")
    op.drop_index("idx_fotos_recientes", table_name="fotos")
    op.drop_index("idx_fotos_pendientes", table_name="fotos")
    op.drop_index("idx_fotos_pantalla", table_name="fotos")
    op.drop_table("fotos")
    op.drop_table("eventos")
    op.drop_table("administradores")
