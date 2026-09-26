"""Modelos SQLAlchemy 2.0. Espejan db/schema.sql exactamente.

Convenciones de la sección 4 de CONSTRUIR-APP.md:
- Todas las marcas de tiempo son timestamptz. Nunca timestamp pelado: el
  servidor está en UTC y el evento en Argentina.
- Los estados son text con CHECK, no tipos ENUM.
- Nada se borra: una foto rechazada sigue existiendo y se puede revertir. Una
  cuenta tampoco se borra: se da de baja, y sus eventos y fotos quedan. La
  única excepción: un superadmin puede eliminar una cuenta para siempre, y sus
  eventos pasan a él (DELETE /api/admin/cuentas/{id}, routers/cuentas.py).
  Con la cuenta se van también sus pedidos de recuperación de contraseña
  (ON DELETE CASCADE): son datos de la persona, no de ningún evento.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Text,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

ESTADOS_EVENTO = ("borrador", "activo", "cerrado")
ESTADOS_FOTO = ("pendiente", "aprobada", "rechazada")
ROLES_USUARIO = ("superadmin", "admin", "organizador")
ESTADOS_CUENTA = ("pendiente", "activa", "baja")
TEMAS_PANEL = ("oscuro", "claro", "automatico")
FONDOS_PANTALLA = ("desenfocado", "negro")
TRANSICIONES_PANTALLA = ("fundido", "corte")


class Base(DeclarativeBase):
    pass


class Usuario(Base):
    """Una cuenta del panel.

    `superadmin` es la dueña de la app: puede todo lo que puede un admin y además
    gestiona a los admins. `admin` ve todos los eventos y todas las cuentas, y
    gestiona las de organizador; `organizador`, sólo ve sus eventos. El
    superadmin no se asigna desde el panel: se nombra a mano con un UPDATE en la
    base.

    Las cuentas se crean desde el registro público y nacen `pendiente`: no
    entran hasta que un admin las pasa a `activa`. Dar de baja es un estado, no
    un DELETE: los eventos y las fotos de la cuenta quedan.

    Eliminar para siempre existe sólo para un superadmin, y nunca sobre otro
    superadmin ni sobre la propia cuenta. Se borra esta fila y nada más: sus
    eventos pasan al superadmin que la elimina y `fotos.moderada_por` queda en
    NULL donde la nombraba.
    """

    __tablename__ = "usuarios"
    __table_args__ = (
        CheckConstraint(
            "rol IN ('superadmin','admin','organizador')", name="usuarios_rol_check"
        ),
        CheckConstraint(
            "estado IN ('pendiente','activa','baja')", name="usuarios_estado_check"
        ),
        CheckConstraint(
            "tema IN ('oscuro','claro','automatico')", name="usuarios_tema_check"
        ),
        CheckConstraint(
            "pred_segundos_por_foto BETWEEN 3 AND 30",
            name="usuarios_pred_segundos_por_foto_check",
        ),
        CheckConstraint(
            "pred_max_fotos_por_dispositivo BETWEEN 1 AND 50",
            name="usuarios_pred_max_fotos_por_dispositivo_check",
        ),
        CheckConstraint(
            "pred_pantalla_fondo IN ('desenfocado','negro')",
            name="usuarios_pred_pantalla_fondo_check",
        ),
        CheckConstraint(
            "pred_pantalla_transicion IN ('fundido','corte')",
            name="usuarios_pred_pantalla_transicion_check",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    nombre: Mapped[str] = mapped_column(Text, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    rol: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'organizador'")
    )
    estado: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'pendiente'")
    )
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Un token de sesión emitido ANTES de este momento ya no sirve
    # (`usuario_actual`, deps.py). Se pone al restablecer la contraseña por
    # email y al cambiarla desde Mi cuenta: así se cierran todas las sesiones
    # abiertas. Va truncado al milisegundo, como el `iat` de los tokens.
    sesiones_desde: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # La foto de la cuenta. Vive en Cloudinary, dentro de `avatares/{id}/`.
    avatar_public_id: Mapped[str | None] = mapped_column(Text)
    avatar_url: Mapped[str | None] = mapped_column(Text)

    # El tema del panel. `automatico` sigue al del sistema operativo.
    tema: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'automatico'")
    )

    # Predeterminados: se copian a cada evento nuevo de esta cuenta, también si
    # un admin se lo crea. Cambiarlos no toca los eventos que ya existen.
    pred_segundos_por_foto: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("7")
    )
    pred_max_fotos_por_dispositivo: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("10")
    )
    pred_pantalla_fondo: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'desenfocado'")
    )
    pred_pantalla_transicion: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'fundido'")
    )
    pred_pantalla_nombre: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    pred_pantalla_qr: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )

    eventos: Mapped[list["Evento"]] = relationship(back_populates="usuario")


class Evento(Base):
    __tablename__ = "eventos"
    __table_args__ = (
        CheckConstraint(
            "estado IN ('borrador','activo','cerrado')", name="eventos_estado_check"
        ),
        CheckConstraint(
            "video_estado IN ('procesando','listo','fallo')", name="eventos_video_estado_check"
        ),
        CheckConstraint(
            "pantalla_fondo IN ('desenfocado','negro')", name="eventos_pantalla_fondo_check"
        ),
        CheckConstraint(
            "pantalla_transicion IN ('fundido','corte')",
            name="eventos_pantalla_transicion_check",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    # El dueño del evento. Un organizador sólo ve los eventos donde es el dueño.
    usuario_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("usuarios.id"), nullable=False
    )
    nombre: Mapped[str] = mapped_column(Text, nullable=False)
    fecha_evento: Mapped[date] = mapped_column(Date, nullable=False)

    # Las dos claves públicas. Se generan con secrets.token_urlsafe, nunca a
    # partir del id ni de la fecha: si fueran adivinables, el aislamiento entre
    # eventos simultáneos no existiría.
    codigo_publico: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    token_pantalla: Mapped[str] = mapped_column(Text, nullable=False, unique=True)

    estado: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'borrador'")
    )
    max_fotos_por_dispositivo: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("10")
    )
    segundos_por_foto: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("7")
    )
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    cerrado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # El video del evento lo arma Cloudinary en segundo plano. Cada pedido usa un
    # public_id nuevo: nada se sobrescribe y el anterior queda disponible.
    video_estado: Mapped[str | None] = mapped_column(Text)
    video_public_id: Mapped[str | None] = mapped_column(Text)
    video_url: Mapped[str | None] = mapped_column(Text)
    video_fotos: Mapped[int | None] = mapped_column(Integer)
    video_pedido_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # A los 30 días de la fecha del evento se borran de Cloudinary todas sus
    # fotos y todos sus videos (app/limpieza.py). Las filas quedan: esto marca
    # que los archivos ya no existen. NULL mientras no se borraron.
    fotos_borradas_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Cómo se ve la pantalla del proyector. Al crear el evento se copian de los
    # predeterminados del dueño; la pantalla los toma en su próxima pasada de
    # polling, sin recargar. `desenfocado`: la misma foto, borrosa, de fondo.
    pantalla_fondo: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'desenfocado'")
    )
    pantalla_transicion: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'fundido'")
    )
    pantalla_mostrar_nombre: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    pantalla_mostrar_qr: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )

    usuario: Mapped[Usuario] = relationship(back_populates="eventos")
    fotos: Mapped[list["Foto"]] = relationship(
        back_populates="evento", cascade="all, delete-orphan"
    )


class Foto(Base):
    __tablename__ = "fotos"
    __table_args__ = (
        CheckConstraint(
            "estado IN ('pendiente','aprobada','rechazada')", name="fotos_estado_check"
        ),
        # El índice del polling de la pantalla. Sin este, a las 200 fotos se arrastra.
        Index("idx_fotos_pantalla", "evento_id", "estado", "id"),
        # Índice parcial: sólo las pendientes. Es el que usa la bandeja de moderación.
        Index(
            "idx_fotos_pendientes",
            "evento_id",
            "id",
            postgresql_where=text("estado = 'pendiente'"),
        ),
        # Para el listado del panel, ordenado por lo más reciente.
        Index("idx_fotos_recientes", "evento_id", text("subida_en DESC")),
        # Para contar cuántas subió un dispositivo.
        Index("idx_fotos_dispositivo", "evento_id", "dispositivo_hash"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    evento_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("eventos.id", ondelete="CASCADE"), nullable=False
    )
    public_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    ancho: Mapped[int | None] = mapped_column(Integer)
    alto: Mapped[int | None] = mapped_column(Integer)
    bytes: Mapped[int | None] = mapped_column(Integer)
    estado: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'pendiente'")
    )
    dispositivo_hash: Mapped[str | None] = mapped_column(Text)
    nombre_invitado: Mapped[str | None] = mapped_column(Text)
    subida_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    moderada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    moderada_por: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("usuarios.id")
    )

    evento: Mapped[Evento] = relationship(back_populates="fotos")


class RecuperacionContrasena(Base):
    """Un pedido de "olvidé mi contraseña" (POST /api/cuentas/recuperar).

    Se guarda el HASH del token (sha256), nunca el token: el token viaja sólo
    en el email. Con una copia de la base no se restablece ninguna cuenta.

    Sirve una vez (`usado_en`) y durante una hora (`vence_en`). Un pedido nuevo
    de la misma cuenta anula los anteriores que seguían vivos (`anulado_en`), y
    cambiar la contraseña también. Nada se borra en el uso normal: la fila
    queda como historial. Sólo se va con la cuenta, si un superadmin la elimina
    (ON DELETE CASCADE).
    """

    __tablename__ = "recuperaciones_contrasena"
    __table_args__ = (
        # Para anular los pedidos vivos de una cuenta y para el CASCADE.
        Index("idx_recuperaciones_usuario", "usuario_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    usuario_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    vence_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    usado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    anulado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
