# Mixins reutilizables para los modelos
from sqlalchemy import Boolean, Column, DateTime, Integer, func, text


class EstadoAuditoriaMixin:
    """Agrega estado (activo/inactivo) y campos de auditoría a un modelo.
    Uso: class Tipo(EstadoAuditoriaMixin, Base). No define __tablename__."""

    # Estado del registro: True = activo, False = inactivo (permite "desactivar" sin borrar)
    estado = Column(Boolean, nullable=False, default=True, server_default=text("1"))

    # Fecha y hora en que se creó el registro (la pone MySQL automáticamente)
    creado_en = Column(DateTime, nullable=False, server_default=func.now())

    # Fecha y hora de la última modificación (se actualiza al editar desde SQLAlchemy)
    actualizado_en = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    # Id del usuario que creó el registro (sin ForeignKey para no atar las tablas entre sí)
    creado_por = Column(Integer, nullable=True)

    # Id del usuario que hizo la última modificación (sin ForeignKey)
    actualizado_por = Column(Integer, nullable=True)
