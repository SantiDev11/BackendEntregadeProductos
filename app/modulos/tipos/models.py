from sqlalchemy import Column, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.config.database import Base
from app.modulos.comun.mixins import EstadoAuditoriaMixin

class Tipo(EstadoAuditoriaMixin, Base):
    __tablename__ = "tipos"
    __table_args__ = (
        # el nombre es único dentro de cada bodega ("Arroz" puede estar en la bodega 1 y en la 2)
        UniqueConstraint("bodega_id", "nombre", name="uq_tipos_bodega_nombre"),
    )

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False)
    # Bodega a la que pertenece el tipo (null = sin bodega: tipos antiguos que solo maneja el admin)
    bodega_id = Column(Integer, ForeignKey("bodegas.id"), nullable=True)

    # Empresa del tipo: la de su bodega (null = tipo general o anterior a las empresas)
    empresa_id = Column(Integer, ForeignKey("empresas.id"), nullable=True)

    bodega = relationship("Bodega")
    empresa = relationship("Empresa")
