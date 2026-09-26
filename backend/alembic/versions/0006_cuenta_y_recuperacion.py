"""Mi cuenta, recuperar la contraseña y el estilo de la pantalla.

Equivalente, en db/schema.sql, a las columnas nuevas de `usuarios` y de
`eventos` y a la tabla `recuperaciones_contrasena`.

- `usuarios.sesiones_desde`: un token emitido antes ya no sirve. Se pone al
  restablecer la contraseña por email y al cambiarla desde Mi cuenta.
- `usuarios.avatar_public_id` y `avatar_url`: la foto de la cuenta, en
  Cloudinary, dentro de `avatares/{id}/`.
- `usuarios.tema`: el tema del panel (`oscuro`, `claro` o `automatico`).
- `usuarios.pred_*`: los predeterminados que se copian a cada evento nuevo de
  la cuenta (segundos por foto, fotos por invitado y el estilo de pantalla).
- `eventos.pantalla_*`: el estilo de la pantalla de cada evento (fondo,
  transición, si muestra el nombre y el QR).
- `recuperaciones_contrasena`: los pedidos de "olvidé mi contraseña", con el
  HASH del token. Se van con la cuenta si un superadmin la elimina (ON DELETE
  CASCADE); nada más los borra.

Todas las columnas nuevas NOT NULL llevan su DEFAULT desde el ADD COLUMN: así
completan las filas que ya existen. Las cuentas quedan con los valores de
siempre (7 s por foto, 10 fotos por invitado, tema automático) y los eventos
con la pantalla como se veía hasta ahora (fondo desenfocado, fundido, con
nombre y con QR). Nadie queda con la sesión cerrada: `sesiones_desde` nace NULL.

Los nombres de las restricciones son los que Postgres le pone a un CHECK en
línea dentro de CREATE TABLE (`{tabla}_{columna}_check`), para que una base
migrada quede igual que una creada desde cero con schema.sql.

OJO con el downgrade: se pierden los avatares guardados (las imágenes quedan en
Cloudinary), los temas, los predeterminados, el estilo de pantalla de cada
evento y el historial de recuperaciones. Y las sesiones que se habían cerrado al
cambiar una contraseña vuelven a servir hasta su vencimiento (12 horas).

Para volver al deploy anterior NO hace falta el downgrade: el código de 3c23aaa
anda sobre este esquema (todo lo nuevo tiene DEFAULT o admite NULL). Lo que lo
frena es su `alembic upgrade head`, que no conoce esta revisión. El
procedimiento, con `alembic stamp` y sin perder nada, está en el README
(«Volver al deploy anterior»). Nunca bajar con la API nueva en marcha: sus
modelos leen estas columnas.

Revision ID: 0006_cuenta_y_recuperacion
Revises: 0005_fotos_borradas
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_cuenta_y_recuperacion"
down_revision = "0005_fotos_borradas"
branch_labels = None
depends_on = None

_COLUMNAS_USUARIOS = (
    "pred_pantalla_qr",
    "pred_pantalla_nombre",
    "pred_pantalla_transicion",
    "pred_pantalla_fondo",
    "pred_max_fotos_por_dispositivo",
    "pred_segundos_por_foto",
    "tema",
    "avatar_url",
    "avatar_public_id",
    "sesiones_desde",
)
_CHECKS_USUARIOS = (
    "usuarios_pred_pantalla_transicion_check",
    "usuarios_pred_pantalla_fondo_check",
    "usuarios_pred_max_fotos_por_dispositivo_check",
    "usuarios_pred_segundos_por_foto_check",
    "usuarios_tema_check",
)
_COLUMNAS_EVENTOS = (
    "pantalla_mostrar_qr",
    "pantalla_mostrar_nombre",
    "pantalla_transicion",
    "pantalla_fondo",
)
_CHECKS_EVENTOS = (
    "eventos_pantalla_transicion_check",
    "eventos_pantalla_fondo_check",
)


def upgrade() -> None:
    # ── usuarios ──────────────────────────────────────────────
    op.add_column("usuarios", sa.Column("sesiones_desde", sa.DateTime(timezone=True), nullable=True))
    op.add_column("usuarios", sa.Column("avatar_public_id", sa.Text(), nullable=True))
    op.add_column("usuarios", sa.Column("avatar_url", sa.Text(), nullable=True))
    op.add_column(
        "usuarios",
        sa.Column("tema", sa.Text(), nullable=False, server_default=sa.text("'automatico'")),
    )
    op.add_column(
        "usuarios",
        sa.Column("pred_segundos_por_foto", sa.Integer(), nullable=False,
                  server_default=sa.text("7")),
    )
    op.add_column(
        "usuarios",
        sa.Column("pred_max_fotos_por_dispositivo", sa.Integer(), nullable=False,
                  server_default=sa.text("10")),
    )
    op.add_column(
        "usuarios",
        sa.Column("pred_pantalla_fondo", sa.Text(), nullable=False,
                  server_default=sa.text("'desenfocado'")),
    )
    op.add_column(
        "usuarios",
        sa.Column("pred_pantalla_transicion", sa.Text(), nullable=False,
                  server_default=sa.text("'fundido'")),
    )
    op.add_column(
        "usuarios",
        sa.Column("pred_pantalla_nombre", sa.Boolean(), nullable=False,
                  server_default=sa.text("true")),
    )
    op.add_column(
        "usuarios",
        sa.Column("pred_pantalla_qr", sa.Boolean(), nullable=False,
                  server_default=sa.text("true")),
    )
    op.create_check_constraint(
        "usuarios_tema_check", "usuarios", "tema IN ('oscuro','claro','automatico')"
    )
    op.create_check_constraint(
        "usuarios_pred_segundos_por_foto_check", "usuarios",
        "pred_segundos_por_foto BETWEEN 3 AND 30",
    )
    op.create_check_constraint(
        "usuarios_pred_max_fotos_por_dispositivo_check", "usuarios",
        "pred_max_fotos_por_dispositivo BETWEEN 1 AND 50",
    )
    op.create_check_constraint(
        "usuarios_pred_pantalla_fondo_check", "usuarios",
        "pred_pantalla_fondo IN ('desenfocado','negro')",
    )
    op.create_check_constraint(
        "usuarios_pred_pantalla_transicion_check", "usuarios",
        "pred_pantalla_transicion IN ('fundido','corte')",
    )

    # ── eventos ───────────────────────────────────────────────
    op.add_column(
        "eventos",
        sa.Column("pantalla_fondo", sa.Text(), nullable=False,
                  server_default=sa.text("'desenfocado'")),
    )
    op.add_column(
        "eventos",
        sa.Column("pantalla_transicion", sa.Text(), nullable=False,
                  server_default=sa.text("'fundido'")),
    )
    op.add_column(
        "eventos",
        sa.Column("pantalla_mostrar_nombre", sa.Boolean(), nullable=False,
                  server_default=sa.text("true")),
    )
    op.add_column(
        "eventos",
        sa.Column("pantalla_mostrar_qr", sa.Boolean(), nullable=False,
                  server_default=sa.text("true")),
    )
    op.create_check_constraint(
        "eventos_pantalla_fondo_check", "eventos", "pantalla_fondo IN ('desenfocado','negro')"
    )
    op.create_check_constraint(
        "eventos_pantalla_transicion_check", "eventos",
        "pantalla_transicion IN ('fundido','corte')",
    )

    # ── recuperaciones_contrasena ─────────────────────────────
    op.create_table(
        "recuperaciones_contrasena",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("usuario_id", sa.BigInteger(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("vence_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("usado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("anulado_en", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="recuperaciones_contrasena_pkey"),
        sa.ForeignKeyConstraint(
            ["usuario_id"], ["usuarios.id"],
            name="recuperaciones_contrasena_usuario_id_fkey", ondelete="CASCADE",
        ),
        sa.UniqueConstraint("token_hash", name="recuperaciones_contrasena_token_hash_key"),
    )
    op.create_index("idx_recuperaciones_usuario", "recuperaciones_contrasena", ["usuario_id"])


def downgrade() -> None:
    op.drop_index("idx_recuperaciones_usuario", table_name="recuperaciones_contrasena")
    op.drop_table("recuperaciones_contrasena")

    for nombre in _CHECKS_EVENTOS:
        op.drop_constraint(nombre, "eventos", type_="check")
    for columna in _COLUMNAS_EVENTOS:
        op.drop_column("eventos", columna)

    for nombre in _CHECKS_USUARIOS:
        op.drop_constraint(nombre, "usuarios", type_="check")
    for columna in _COLUMNAS_USUARIOS:
        op.drop_column("usuarios", columna)
