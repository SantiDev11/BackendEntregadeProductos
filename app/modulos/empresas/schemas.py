# Esquemas de Empresa (entrada, salida y listado paginado)
from datetime import datetime
from typing import Annotated, List, Optional

from pydantic import (AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints, ValidationInfo,
                      field_validator)
from pydantic_core import PydanticCustomError

ESTADOS_DESTINO = ("activa", "rechazada", "suspendida")  # a "pendiente" no se puede volver
MSG_ESTADO = "debe ser activa, rechazada o suspendida"
MSG_MOTIVO_FALTA = "es obligatorio"
MSG_MOTIVO_CORTO = "debe tener al menos 10 caracteres"
MSG_MOTIVO_LARGO = "es demasiado largo"


def _normalizar(valor):
    """"Activa " -> "activa" antes de validar."""
    return valor.strip().lower() if isinstance(valor, str) else valor


def _validar_estado(valor: str) -> str:
    if valor not in ESTADOS_DESTINO:
        raise PydanticCustomError("estado", MSG_ESTADO)
    return valor


EstadoDestino = Annotated[str, BeforeValidator(_normalizar), AfterValidator(_validar_estado)]


class EmpresaResumen(BaseModel):
    """Empresa de un usuario, como va en /login y /me."""
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(examples=[1])
    razon_social: str = Field(examples=["Distribuidora Andina S.A.S."])
    estado: str = Field(description="`pendiente`, `activa`, `rechazada` o `suspendida`.", examples=["activa"])


class EmpresaEstadoUpdate(BaseModel):
    """Nuevo estado de la empresa."""
    model_config = ConfigDict(json_schema_extra={"examples": [
        {"estado": "activa"}, {"estado": "rechazada", "motivo_rechazo": "El NIT no coincide con el RUT"}]})

    estado: EstadoDestino = Field(description="**Obligatorio.** `activa`, `rechazada` o `suspendida`.", examples=["rechazada"])
    motivo_rechazo: Optional[Annotated[str, StringConstraints(strip_whitespace=True)]] = Field(
        default=None, validate_default=True,
        description="**Obligatorio solo al rechazar**, de 10 a 255 caracteres. Con otro estado se ignora.",
        examples=["El NIT no coincide con el RUT"])

    @field_validator("motivo_rechazo", mode="after")
    @classmethod
    def motivo_segun_estado(cls, valor, info: ValidationInfo):
        if info.data.get("estado") != "rechazada":
            return None
        if valor is None:
            raise PydanticCustomError("motivo", MSG_MOTIVO_FALTA)
        if len(valor) < 10:
            raise PydanticCustomError("motivo", MSG_MOTIVO_CORTO)
        if len(valor) > 255:
            raise PydanticCustomError("motivo", MSG_MOTIVO_LARGO)
        return valor


class EmpresaOut(BaseModel):
    """Empresa como la ve el admin."""
    id: int = Field(examples=[1])
    razon_social: str = Field(examples=["Distribuidora Andina S.A.S."])
    nit: Optional[str] = Field(default=None, description="Con su dígito de verificación.", examples=["900123456-1"])
    correo: Optional[str] = Field(default=None, examples=["empresa@entrega.com"])
    telefono: Optional[str] = Field(default=None, examples=["3001234567"])
    direccion: Optional[str] = Field(default=None, examples=["Calle 10 # 20-30"])
    representante: Optional[str] = Field(default=None, examples=["Ana Torres"])
    estado: str = Field(description="`pendiente`, `activa`, `rechazada` o `suspendida`.", examples=["pendiente"])
    motivo_rechazo: Optional[str] = Field(default=None, description="Solo si está rechazada.")
    fecha_registro: datetime = Field(examples=["2026-11-24T10:30:00"])
    total_bodegueros: int = Field(examples=[0])
    total_bodegas: int = Field(examples=[0])
    total_facturas: int = Field(examples=[0])


class EmpresaPaginado(BaseModel):
    """Respuesta del listado: {data, total, page, limit}."""
    data: List[EmpresaOut] = Field(description="Empresas de la página, de la más reciente a la más antigua.")
    total: int = Field(description="Cantidad total de empresas que cumplen los filtros (no solo las de esta página).", examples=[3])
    page: int = Field(description="Página devuelta (empieza en 1).", examples=[1])
    limit: int = Field(description="Cantidad máxima de elementos por página.", examples=[10])
