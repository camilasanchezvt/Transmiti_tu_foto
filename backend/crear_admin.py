"""Imprime el INSERT del primer administrador para pegar en el SQL Editor de Supabase.

En producción no se corre el seed (vacía las tablas y carga datos de prueba),
así que el administrador se crea a mano. La contraseña se pide por consola y
no queda escrita en ningún archivo; sólo sale el hash.

    cd backend && python crear_admin.py
"""

from __future__ import annotations

from getpass import getpass

from app.security import hashear_password


def _sql(texto: str) -> str:
    return "'" + texto.replace("'", "''") + "'"


def main() -> None:
    email = input("Email del administrador: ").strip().lower()
    nombre = input("Nombre: ").strip()
    password = getpass("Contraseña (no se muestra): ")
    if len(password) < 10:
        raise SystemExit("La contraseña tiene que tener 10 caracteres o más.")
    if password != getpass("Repetila: "):
        raise SystemExit("Las contraseñas no coinciden.")

    print()
    print("INSERT INTO administradores (email, nombre, password_hash) VALUES")
    print(f"  ({_sql(email)}, {_sql(nombre)}, {_sql(hashear_password(password))});")


if __name__ == "__main__":
    main()
