# Esquemas de la búsqueda de clientes
from typing import Annotated, List, Optional

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints, WithJsonSchema
from pydantic_core import PydanticCustomError

MIN_BUSQUEDA = 3  # lo pidió el frontend (antes 5)
MSG_BUSQUEDA_CORTA = f"debe tener al menos {MIN_BUSQUEDA} caracteres"


def _validar_busqueda(valor: str) -> str:
    if len(valor) < MIN_BUSQUEDA:
        raise PydanticCustomError("busqueda_corta", MSG_BUSQUEDA_CORTA)
    return valor


# Texto a buscar: se quitan los espacios al inicio y al final y luego debe tener al menos MIN_BUSQUEDA caracteres
TextoBusqueda = Annotated[str, StringConstraints(strip_whitespace=True), AfterValidator(_validar_busqueda),
                          WithJsonSchema({"type": "string", "minLength": MIN_BUSQUEDA})]


class ClienteOpcion(BaseModel):
    """Cliente disponible para facturar (solo los datos necesarios para elegirlo)."""
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(description="Id del usuario cliente (se envía como `cliente_id`).", examples=[3])
    nombre: str = Field(examples=["Cliente Prueba"])
    tipo_documento: Optional[str] = Field(default=None, examples=["CC"])
    numero_documento: Optional[str] = Field(default=None, examples=["1020304050"])


class ClientePaginado(BaseModel):
    """Respuesta de GET /clientes/buscar y de GET /facturas/clientes: {data, total, page, limit}."""
    data: List[ClienteOpcion] = Field(description="Clientes activos de la página, ordenados por nombre.")
    total: int = Field(description="Cantidad total de clientes que cumplen la búsqueda.", examples=[1])
    page: int = Field(description="Página devuelta (empieza en 1).", examples=[1])
    limit: int = Field(description="Cantidad máxima de elementos por página.", examples=[10])
