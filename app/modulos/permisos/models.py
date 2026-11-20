from sqlalchemy import Column, Integer, String
from app.database import Base
from app.modulos.comun.mixins import EstadoAuditoriaMixin

class Permiso(EstadoAuditoriaMixin, Base):
    __tablename__ = "permisos"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False, unique=True)
    descripcion = Column(String(255), nullable=True)
