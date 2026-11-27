from sqlalchemy import Boolean, Column, Integer, String, ForeignKey, Table, text
from sqlalchemy.orm import relationship

from app.config.database import Base
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
    # Empresa del usuario (null = admin, clientes y usuarios anteriores a las empresas)
    empresa_id = Column(Integer, ForeignKey("empresas.id"), nullable=True)

    # True = está inactivo porque su empresa se suspendió (no porque alguien lo desactivó): al reactivarla vuelve a activo
    desactivado_por_empresa = Column(Boolean, nullable=False, default=False, server_default=text("0"))
    # True = está inactivo porque su rol se desactivó: al reactivar el rol vuelve a activo (si su empresa no lo frena)
    desactivado_por_rol = Column(Boolean, nullable=False, default=False, server_default=text("0"))

    # Datos para facturar (todos opcionales)
    tipo_documento = Column(String(10), nullable=True)  # CC, NIT, CE o PA
    numero_documento = Column(String(30), nullable=True, unique=True)  # número de documento (único)
    telefono = Column(String(30), nullable=True)  # teléfono del usuario
    direccion = Column(String(200), nullable=True)  # dirección del usuario
    ciudad = Column(String(100), nullable=True)  # ciudad del usuario

    rol = relationship("Rol")
    empresa = relationship("Empresa")
    permisos = relationship("Permiso", secondary=usuario_permisos, order_by="Permiso.id")  # permisos efectivos

    @property
    def empresa_estado(self) -> str | None:
        """Estado de su empresa (pendiente, activa, rechazada o suspendida), o None si no tiene."""
        return self.empresa.estado if self.empresa is not None else None
