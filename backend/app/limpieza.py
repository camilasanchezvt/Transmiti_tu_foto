"""Borrado automático de Cloudinary a los 30 días de la fecha del evento.

Qué se borra: TODAS las fotos del evento (aprobadas, pendientes y rechazadas) y
TODOS sus videos (cada "Crear de nuevo" deja uno). Qué no se borra: las filas de
la base. La regla "nada se borra" es sobre la base; los archivos de Cloudinary
se borran porque así lo decidió la usuaria, y la fila del evento queda marcada
con `fotos_borradas_en`.

Cuándo: el día `fotos_se_borran_el` = fecha_evento + 30 días, o en la primera
pasada después. "Hoy" es el de Argentina (UTC−3 fijo), igual que en el panel.

Cómo: una tarea en segundo plano del lifespan de main.py corre
`pasada_de_limpieza` ~60 s después del arranque y después cada 6 horas. Render
gratuito duerme el servicio cuando nadie lo usa, así que en la práctica la
pasada que borra es la de cada arranque: un evento vencido se borra la primera
vez que alguien despierta la API después de su fecha.

Si Cloudinary falla, el evento NO se marca y la pasada siguiente lo reintenta.
Borrar lo que ya no está no es error, así que reintentar es seguro.

Desde el día del borrado, aunque la pasada todavía no haya corrido, el backend
ya no ofrece ni sirve los archivos del evento (`archivos_vencidos`): así una
descarga nunca queda a mitad de camino con la pasada borrando por detrás.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Iterable
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .cloudinary_service import ErrorBorrado, borrar_archivos_del_evento
from .database import SessionLocal
from .fechas import hoy_en_argentina
from .models import Evento

# Hijo del de uvicorn, que en Render sale en el log a nivel INFO (el de
# `app.*` sólo mostraría los errores). Así queda a la vista qué se borró.
log = logging.getLogger("uvicorn.error").getChild("limpieza")

DIAS_HASTA_BORRAR = 30

# La primera pasada espera un poco: el arranque y el health check de Render no
# tienen por qué esperar a Cloudinary. Después, cada seis horas.
ESPERA_INICIAL_S = 60.0
INTERVALO_S = 6 * 60 * 60.0


def fotos_se_borran_el(fecha_evento: date) -> date:
    """El día en que se borran las fotos y el video del evento."""
    return fecha_evento + timedelta(days=DIAS_HASTA_BORRAR)


def fecha_vencida(fecha_evento: date, hoy: date | None = None) -> bool:
    """True desde el día del borrado de un evento con esa fecha: el mismo corte
    que usa `eventos_vencidos` (fecha_evento + 30 <= hoy).

    `hoy_en_argentina` se busca en este módulo al llamar, no al importar: las
    pruebas fijan el "hoy" de todo el borrado con un solo monkeypatch sobre
    `limpieza.hoy_en_argentina`.
    """
    if hoy is None:
        hoy = hoy_en_argentina()
    return fotos_se_borran_el(fecha_evento) <= hoy


def archivos_vencidos(evento: Evento, hoy: date | None = None) -> bool:
    """¿Los archivos del evento ya no se ofrecen ni se sirven?

    Sí cuando ya se borraron, y también desde el día del borrado aunque la
    pasada todavía no haya corrido. Es EL criterio de todo el backend (descarga,
    video, pantalla, reabrir, `video_url_listo`) y no `fotos_borradas_en` solo,
    por dos razones:

    - La pasada corre en cualquier momento de ese día. En Render gratuito, ~60 s
      después de que alguien despierta la API, que suele ser la organizadora
      entrando a descargar: la pasada borraba en plena descarga y el ZIP salía
      incompleto sin avisar.
    - Si Cloudinary falla a mitad (se borraron las imágenes y los videos no), el
      evento no se marca hasta la pasada siguiente. Con el corte por fecha, en
      el medio nadie recibe un ZIP vacío ni URLs muertas.
    """
    return evento.fotos_borradas_en is not None or fecha_vencida(evento.fecha_evento, hoy)


def eventos_vencidos(
    db: Session,
    hoy: date,
    *,
    excluir: Iterable[int] = (),
    limite: int | None = None,
) -> list[Evento]:
    """Los eventos cuyos archivos hay que borrar: sin `fotos_borradas_en` y con
    fecha_evento + 30 <= hoy.

    Se toman con FOR NO KEY UPDATE SKIP LOCKED: si otra pasada (otro worker, o
    la del arranque pisándose con la de las 6 h) ya tiene uno, éste lo saltea
    en vez de esperarlo o de borrarlo de nuevo. NO KEY y no FOR UPDATE a secas
    para no frenar el alta de una foto de ese evento, que sólo necesita la
    clave de la fila (FOR KEY SHARE, por la clave foránea).

    Los locks duran lo que la transacción de `db`.
    """
    consulta = (
        select(Evento)
        .where(
            Evento.fotos_borradas_en.is_(None),
            Evento.fecha_evento <= hoy - timedelta(days=DIAS_HASTA_BORRAR),
        )
        .order_by(Evento.fecha_evento, Evento.id)
        .with_for_update(skip_locked=True, key_share=True)
    )
    excluidos = list(excluir)
    if excluidos:
        consulta = consulta.where(Evento.id.not_in(excluidos))
    if limite is not None:
        consulta = consulta.limit(limite)
    return list(db.scalars(consulta))


def _borrar_y_marcar(evento: Evento) -> bool:
    """Borra los archivos del evento en Cloudinary y, si salió bien, lo marca.

    Un evento todavía abierto (o sin publicar) se cierra: nadie tiene que poder
    subir una foto que no se va a borrar nunca, porque el evento ya figura
    como borrado.
    """
    try:
        borrados = borrar_archivos_del_evento(evento.codigo_publico)
    except ErrorBorrado as e:
        # El mensaje de ErrorBorrado nunca lleva el secreto: sólo el código
        # HTTP y el principio de la respuesta de Cloudinary.
        log.error(
            "limpieza: no se pudieron borrar los archivos del evento %s (%s); "
            "se reintenta en la próxima pasada",
            evento.id, e,
        )
        return False

    ahora = datetime.now(timezone.utc)
    evento.fotos_borradas_en = ahora
    if evento.estado in ("activo", "borrador"):
        evento.estado = "cerrado"
        evento.cerrado_en = ahora
    log.info("limpieza: evento %s, %s archivos borrados de Cloudinary", evento.id, borrados)
    return True


def pasada_de_limpieza(
    hoy: date | None = None,
    fabrica_de_sesiones: Callable[[], Session] | None = None,
) -> int:
    """Procesa todos los eventos vencidos y devuelve cuántos borró.

    De a un evento por transacción: se toma uno (SKIP LOCKED), se borra en
    Cloudinary, se marca y se confirma. Así el lock dura un solo evento, y un
    corte a mitad de la pasada no pierde lo que ya se hizo. Los que fallan en
    esta pasada no se vuelven a tomar hasta la siguiente.

    Nunca levanta una excepción: corre en segundo plano y una base dormida o una
    red caída no pueden tirar abajo la API. Queda en el log y la próxima pasada
    lo vuelve a intentar.
    """
    borrados = 0
    try:
        if hoy is None:
            hoy = hoy_en_argentina()
        if fabrica_de_sesiones is None:
            fabrica_de_sesiones = SessionLocal
        intentados: list[int] = []
        while True:
            with fabrica_de_sesiones() as db:
                tomados = eventos_vencidos(db, hoy, excluir=intentados, limite=1)
                if not tomados:
                    break
                evento = tomados[0]
                intentados.append(evento.id)
                if _borrar_y_marcar(evento):
                    db.commit()
                    borrados += 1
                else:
                    db.rollback()
    except Exception:
        log.exception("limpieza: la pasada se cortó; se retoma en la próxima")
    return borrados


async def bucle_de_limpieza() -> None:
    """La tarea del lifespan: espera, pasa, y vuelve a pasar cada 6 horas.

    La pasada corre en un thread porque httpx y SQLAlchemy son sincrónicos: en
    el loop de eventos frenaría todos los pedidos mientras espera a Cloudinary.
    Se cancela sola cuando la app se apaga.
    """
    await asyncio.sleep(ESPERA_INICIAL_S)
    while True:
        try:
            await asyncio.to_thread(pasada_de_limpieza)
        except Exception:
            # pasada_de_limpieza no levanta; esto es por si falla el thread mismo.
            log.exception("limpieza: no se pudo correr la pasada")
        await asyncio.sleep(INTERVALO_S)
