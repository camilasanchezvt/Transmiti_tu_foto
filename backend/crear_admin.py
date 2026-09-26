"""Imprime el INSERT de la primera cuenta para pegar en el SQL Editor de Supabase.

En producción no se corre el seed (vacía las tablas y carga datos de prueba),
así que la primera cuenta se crea a mano. La contraseña se pide por consola y
no queda escrita en ningún archivo; sólo sale el hash.

Pregunta el rol: `superadmin` (por defecto), que es la dueña de la app y
gestiona a los admins, o `admin`. La cuenta sale `activa`, lista para entrar.

Las demás cuentas no se crean acá: se registran solas desde /admin/registro y
un admin las habilita desde el panel. Este script es sólo para la primera, que
no tiene a quién pedirle que la habilite. Para nombrar superadmin a una cuenta
que ya existe no hace falta el script: alcanza con el UPDATE que explica la
sección 5 de CONSTRUIR-APP.md.

    cd backend && python crear_admin.py
"""

from __future__ import annotations

from getpass import getpass

from app.security import hashear_password

ROLES = ("superadmin", "admin")


def _sql(texto: str) -> str:
    return "'" + texto.replace("'", "''") + "'"


def insert(email: str, nombre: str, password_hash: str, rol: str) -> str:
    """El INSERT listo para pegar. Aparte de main() para poder probarlo."""
    if rol not in ROLES:
        raise ValueError(f"rol inválido: {rol}")
    return (
        "INSERT INTO usuarios (email, nombre, password_hash, rol, estado) VALUES\n"
        f"  ({_sql(email)}, {_sql(nombre)}, {_sql(password_hash)}, {_sql(rol)}, 'activa');"
    )


def main() -> None:
    email = input("Email: ").strip().lower()
    nombre = input("Nombre: ").strip()
    rol = input("Rol, superadmin o admin [superadmin]: ").strip().lower() or "superadmin"
    if rol not in ROLES:
        raise SystemExit("El rol tiene que ser superadmin o admin.")
    password = getpass("Contraseña (no se muestra): ")
    if len(password) < 10:
        raise SystemExit("La contraseña tiene que tener 10 caracteres o más.")
    if password != getpass("Repetila: "):
        raise SystemExit("Las contraseñas no coinciden.")

    print()
    print(insert(email, nombre, hashear_password(password), rol))


if __name__ == "__main__":
    main()
