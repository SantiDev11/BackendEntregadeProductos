from sqlalchemy import Column, Integer, String, ForeignKey, Table
from sqlalchemy.orm import relationship
from app.database import Base
from app.modulos.comun.mixins import EstadoAuditoriaMixin

# Tabla intermedia: un rol tiene muchos permisos y un permiso está en muchos roles
rol_permiso = Table(
    "rol_permiso",
    Base.metadata,
    Column("rol_id", Integer, ForeignKey("roles.id"), primary_key=True),
    Column("permiso_id", Integer, ForeignKey("permisos.id"), primary_key=True),
)

class Rol(EstadoAuditoriaMixin, Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(50), nullable=False, unique=True)
    descripcion = Column(String(255), nullable=True)

    permisos = relationship("Permiso", secondary=rol_permiso)
