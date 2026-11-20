from sqlalchemy import Column, Integer, String, ForeignKey, Table
from sqlalchemy.orm import relationship
from app.database import Base
from app.modulos.comun.mixins import EstadoAuditoriaMixin

# Tabla intermedia: permisos de cada usuario (son sus permisos efectivos).
# El rol solo sirve de plantilla: al crear el usuario se copian los permisos de su rol.
usuario_permisos = Table(
    "usuario_permisos",
    Base.metadata,
    Column("usuario_id", Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), primary_key=True),
    Column("permiso_id", Integer, ForeignKey("permisos.id"), primary_key=True),
)


class Usuario(EstadoAuditoriaMixin, Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False)
    correo = Column(String(100), nullable=False, unique=True)
    contrasena = Column(String(255), nullable=False)  # aquí va el hash bcrypt, nunca texto plano
    rol_id = Column(Integer, ForeignKey("roles.id"), nullable=False)

    # Datos para facturar (todos opcionales)
    tipo_documento = Column(String(10), nullable=True)  # CC, NIT, CE o PA
    numero_documento = Column(String(30), nullable=True, unique=True)  # número de documento (único)
    telefono = Column(String(30), nullable=True)  # teléfono del usuario
    direccion = Column(String(200), nullable=True)  # dirección del usuario
    ciudad = Column(String(100), nullable=True)  # ciudad del usuario

    rol = relationship("Rol")
    permisos = relationship("Permiso", secondary=usuario_permisos, order_by="Permiso.id")  # permisos efectivos
