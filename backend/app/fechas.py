"""La fecha de hoy según Argentina, que es donde pasan los eventos.

Vive aparte porque la usan dos lados que no tienen que conocerse: el listado del
panel (regla de medianoche) y la limpieza de Cloudinary (borrado a los 30 días).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

# Zona fija UTC-3 y no zoneinfo: en Windows zoneinfo no trae la base de zonas y
# rompe las pruebas, y Argentina no tiene horario de verano desde 2009.
ARGENTINA = timezone(timedelta(hours=-3))


def hoy_en_argentina() -> date:
    """El servidor está en UTC: a las 22 h de un sábado en Buenos Aires ya es
    domingo en el servidor, y un evento de esa noche que todavía no se publicó
    pasaría al historial antes de tiempo."""
    return datetime.now(ARGENTINA).date()
