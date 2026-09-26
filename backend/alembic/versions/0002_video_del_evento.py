"""Video del evento: estado del pedido a Cloudinary y la URL resultante.

Equivalente a las columnas video_* de db/schema.sql.

Revision ID: 0002_video_del_evento
Revises: 0001_esquema_inicial
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_video_del_evento"
down_revision = "0001_esquema_inicial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("eventos", sa.Column("video_estado", sa.Text(), nullable=True))
    op.add_column("eventos", sa.Column("video_public_id", sa.Text(), nullable=True))
    op.add_column("eventos", sa.Column("video_url", sa.Text(), nullable=True))
    op.add_column("eventos", sa.Column("video_fotos", sa.Integer(), nullable=True))
    op.add_column(
        "eventos", sa.Column("video_pedido_en", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_check_constraint(
        "eventos_video_estado_check",
        "eventos",
        "video_estado IN ('procesando','listo','fallo')",
    )


def downgrade() -> None:
    op.drop_constraint("eventos_video_estado_check", "eventos", type_="check")
    for columna in ("video_pedido_en", "video_fotos", "video_url", "video_public_id", "video_estado"):
        op.drop_column("eventos", columna)
