"""Modelos SQLAlchemy 2.0. Espejan db/schema.sql exactamente.

Convenciones de la sección 4 de CONSTRUIR-APP.md:
- Todas las marcas de tiempo son timestamptz. Nunca timestamp pelado: el
  servidor está en UTC y el evento en Argentina.
- Los estados son text con CHECK, no tipos ENUM.
- Nada se borra: una foto rechazada sigue existiendo y se puede revertir.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
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


class Base(DeclarativeBase):
    pass


class Administrador(Base):
    __tablename__ = "administradores"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    nombre: Mapped[str] = mapped_column(Text, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    eventos: Mapped[list["Evento"]] = relationship(back_populates="admin")


class Evento(Base):
    __tablename__ = "eventos"
    __table_args__ = (
        CheckConstraint(
            "estado IN ('borrador','activo','cerrado')", name="eventos_estado_check"
        ),
        CheckConstraint(
            "video_estado IN ('procesando','listo','fallo')", name="eventos_video_estado_check"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    admin_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("administradores.id"), nullable=False
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

    admin: Mapped[Administrador] = relationship(back_populates="eventos")
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
        BigInteger, ForeignKey("administradores.id")
    )

    evento: Mapped[Evento] = relationship(back_populates="fotos")
