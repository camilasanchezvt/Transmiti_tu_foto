"""Borrado automático de Cloudinary: cuándo se borraron los archivos de un evento.

Equivalente a `eventos.fotos_borradas_en` en db/schema.sql.

A los 30 días de la fecha del evento, app/limpieza.py borra de Cloudinary todas
sus fotos y todos sus videos. Las filas de `fotos` y de `eventos` quedan (nada
se borra de la base): esta columna marca que los archivos ya no existen. NULL
mientras no se borraron, que es como quedan todos los eventos existentes.

La migración no borra nada: la primera pasada de limpieza, unos segundos después
de arrancar, se encarga de los eventos que ya estaban vencidos.

Revision ID: 0005_fotos_borradas
Revises: 0004_superadmin
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005_fotos_borradas"
down_revision = "0004_superadmin"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "eventos", sa.Column("fotos_borradas_en", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("eventos", "fotos_borradas_en")
