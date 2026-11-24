from sqlalchemy import CheckConstraint, Column, DateTime, Integer, String, UniqueConstraint, func

from app.config.database import Base

# Estados de una empresa. Se registra "pendiente" y el admin la aprueba, la rechaza o la suspende
ESTADOS_EMPRESA = ["pendiente", "activa", "rechazada", "suspendida"]


class Empresa(Base):
    """No usa EstadoAuditoriaMixin: aquí `estado` es un texto (ESTADOS_EMPRESA), no activo/inactivo."""
    __tablename__ = "empresas"
    __table_args__ = (
        UniqueConstraint("nit", name="uq_empresas_nit"),
        CheckConstraint("estado IN ('pendiente', 'activa', 'rechazada', 'suspendida')", name="ck_empresas_estado"),
    )

    id = Column(Integer, primary_key=True, index=True)
    razon_social = Column(String(100), nullable=False)

    # Datos del registro (el NIT se guarda sin el dígito de verificación, que va aparte: 900123456-1 -> nit y dv)
    nit = Column(String(20), nullable=True)
    dv = Column(String(1), nullable=True)
    correo = Column(String(100), nullable=True)
    telefono = Column(String(30), nullable=True)
    direccion = Column(String(200), nullable=True)
    representante = Column(String(100), nullable=True)  # representante legal

    estado = Column(String(20), nullable=False, default="pendiente", server_default="pendiente", index=True)
    motivo_rechazo = Column(String(255), nullable=True)  # por qué el admin la rechazó

    creado_en = Column(DateTime, nullable=False, server_default=func.now())
    actualizado_en = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    @property
    def nit_completo(self) -> str | None:
        """NIT con su dígito de verificación: 900123456-1."""
        return f"{self.nit}-{self.dv}" if self.nit and self.dv else self.nit
