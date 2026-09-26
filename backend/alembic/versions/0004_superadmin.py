"""Tercer rol: `superadmin`, la dueña de la app.

Equivalente al CHECK de `usuarios.rol` en db/schema.sql.

El superadmin puede todo lo que puede un admin y además gestiona a los admins:
les cambia el rol, los da de baja y los reactiva. Un admin sólo gestiona
organizadores. La matriz completa está en la sección 5 de CONSTRUIR-APP.md.

La migración sólo amplía el CHECK. No promueve a nadie: el superadmin se nombra
a mano con un UPDATE en la base, y su email no va en el código ni en la
documentación porque el repositorio es público. El panel tampoco lo asigna.

OJO con el downgrade: el esquema anterior no tiene este rol, así que los
superadmin vuelven a ser `admin` antes de restaurar el CHECK. Siguen entrando y
viendo todo, pero ya no pueden gestionar a otros admins.

Revision ID: 0004_superadmin
Revises: 0003_usuarios_y_roles
"""

from __future__ import annotations

from alembic import op

revision = "0004_superadmin"
down_revision = "0003_usuarios_y_roles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("usuarios_rol_check", "usuarios", type_="check")
    op.create_check_constraint(
        "usuarios_rol_check", "usuarios", "rol IN ('superadmin','admin','organizador')"
    )


def downgrade() -> None:
    op.drop_constraint("usuarios_rol_check", "usuarios", type_="check")
    op.execute("UPDATE usuarios SET rol = 'admin' WHERE rol = 'superadmin'")
    op.create_check_constraint(
        "usuarios_rol_check", "usuarios", "rol IN ('admin','organizador')"
    )
