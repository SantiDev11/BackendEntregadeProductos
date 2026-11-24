from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.config.database import Base
from app.modulos.comun.mixins import EstadoAuditoriaMixin

class Bodega(EstadoAuditoriaMixin, Base):
    __tablename__ = "bodegas"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False, unique=True)
    direccion = Column(String(200), nullable=True)

    # Datos para facturar (todos opcionales)
    codigo = Column(String(30), nullable=True, unique=True)  # código interno, se guarda en mayúsculas
    ciudad = Column(String(100), nullable=True)  # ciudad de la bodega
    departamento = Column(String(100), nullable=True)  # departamento de la bodega
    telefono = Column(String(30), nullable=True)  # teléfono de la bodega
    correo = Column(String(100), nullable=True)  # correo de la bodega

    # Persona que recibe la mercancía en la bodega
    recibe_nombre = Column(String(100), nullable=True)  # nombre de quien recibe
    recibe_documento = Column(String(30), nullable=True)  # documento de quien recibe
    recibe_cargo = Column(String(100), nullable=True)  # cargo de quien recibe
    recibe_telefono = Column(String(30), nullable=True)  # teléfono de quien recibe

    # Dueño de la bodega: el bodeguero que la administra (null = sin asignar, solo la maneja el admin)
    bodeguero_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    # Empresa de la bodega (null = bodega anterior a las empresas)
    empresa_id = Column(Integer, ForeignKey("empresas.id"), nullable=True)

    bodeguero = relationship("Usuario")
    empresa = relationship("Empresa")
