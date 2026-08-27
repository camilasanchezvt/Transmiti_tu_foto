"""Motor, sesión y dependencia de base de datos.

En Supabase, DATABASE_URL tiene que ser la cadena del POOLER EN MODO SESIÓN:
la conexión directa resuelve por IPv6 y falla desde Render con un error de red
que parece de credenciales.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .config import obtener_config

config = obtener_config()

motor = create_engine(
    config.DATABASE_URL,
    # Render duerme el servicio y el pooler corta conexiones ociosas. Sin esto,
    # el primer pedido después de un rato muere con "server closed the connection".
    pool_pre_ping=True,
    pool_recycle=1800,
    # Sin timeout, un host que no contesta deja el pedido colgado hasta que se
    # rinde TCP, que en Windows son más de un minuto. Pasa de verdad en dos
    # casos: cuando Supabase gratuito se pausó, y cuando la cadena apunta a la
    # conexión directa en vez del pooler y el nombre resuelve por IPv6.
    # Es preferible un error claro a los cinco segundos que un worker tomado.
    connect_args={"connect_timeout": 5},
    echo=False,
)

SessionLocal = sessionmaker(bind=motor, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    sesion = SessionLocal()
    try:
        yield sesion
    finally:
        sesion.close()
