# Esquemas de Tipo (entrada, salida y listado paginado)
from datetime import datetime
from typing import Annotated, List, Optional

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.modulos.comun.validadores import Entero

# Nombre: se quitan los espacios al inicio y al final y luego debe tener de 1 a 100 caracteres
NombreTipo = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class TipoCreate(BaseModel):
    """Datos para crear un tipo (los campos de auditoría los pone el servidor)."""
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"nombre": "Alimentos", "bodega_id": 1, "estado": True}]}
    )

    nombre: NombreTipo = Field(
        description="**Obligatorio.** Nombre del tipo, de 1 a 100 caracteres. "
                    "Se quitan los espacios al inicio y al final. "
                    "Debe ser único **dentro de su bodega** (sin distinguir mayúsculas).",
        examples=["Alimentos"],
    )
    bodega_id: Optional[Entero] = Field(
        default=None,
        description="Bodega del tipo. **Admin:** la elige (si no la envía, el tipo queda sin bodega). "
                    "**Otros usuarios:** se asigna sola si tienen una bodega; si tienen varias, deben enviar una de las suyas.",
        examples=[1],
    )
    estado: bool = Field(
        default=True,
        description="Opcional. `true` = activo, `false` = inactivo. Si no se envía, queda activo.",
        examples=[True],
    )


class TipoUpdate(BaseModel):
    """Datos para editar un tipo (todos opcionales; los de auditoría los pone el servidor)."""
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"nombre": "Alimentos y Bebidas", "estado": False}]}
    )

    nombre: Optional[NombreTipo] = Field(
        default=None,
        description="Opcional. Nuevo nombre, de 1 a 100 caracteres, único dentro de su bodega (sin distinguir mayúsculas). "
                    "Si no se envía o llega en `null`, no se cambia.",
        examples=["Alimentos y Bebidas"],
    )
    bodega_id: Optional[Entero] = Field(
        default=None,
        description="Opcional, **solo admin**: mueve el tipo a otra bodega. Si lo envía otro usuario, se ignora.",
        examples=[2],
    )
    estado: Optional[bool] = Field(
        default=None,
        description="Opcional. `true` activa y `false` desactiva el tipo. "
                    "Si no se envía o llega en `null`, no se cambia.",
        examples=[False],
    )


class TipoOut(BaseModel):
    """Tipo tal como se devuelve al frontend."""
    model_config = ConfigDict(
        from_attributes=True,  # permite crearlo desde el modelo de SQLAlchemy
        json_schema_extra={
            "examples": [{
                "id": 1,
                "nombre": "Alimentos",
                "bodega_id": 1,
                "bodega_nombre": "Bodega Central",
                "estado": True,
                "creado_en": "2026-11-18T10:30:00",
                "actualizado_en": "2026-11-18T10:30:00",
                "creado_por": 1,
                "actualizado_por": 1,
            }]
        },
    )

    id: int = Field(description="Id del tipo (lo genera el servidor).", examples=[1])
    nombre: str = Field(description="Nombre del tipo.", examples=["Alimentos"])
    bodega_id: Optional[int] = Field(default=None, description="Bodega a la que pertenece, o `null` si no tiene.", examples=[1])
    bodega_nombre: Optional[str] = Field(default=None, validation_alias="bodega",
                                         description="Nombre de la bodega, o `null`.", examples=["Bodega Central"])
    estado: bool = Field(description="`true` = activo, `false` = inactivo.", examples=[True])
    creado_en: datetime = Field(description="Fecha y hora de creación (la pone el servidor).",
                                examples=["2026-11-18T10:30:00"])
    actualizado_en: datetime = Field(description="Fecha y hora de la última modificación (la pone el servidor).",
                                     examples=["2026-11-18T10:30:00"])
    creado_por: Optional[int] = Field(default=None,
                                      description="Id del usuario que lo creó (lo pone el servidor).",
                                      examples=[1])
    actualizado_por: Optional[int] = Field(default=None,
                                           description="Id del usuario que lo modificó por última vez (lo pone el servidor).",
                                           examples=[1])

    @field_validator("bodega_nombre", mode="before")
    @classmethod
    def nombre_de_la_bodega(cls, valor):
        """El modelo entrega el objeto Bodega (relación "bodega"); aquí se convierte en su nombre."""
        return valor.nombre if hasattr(valor, "nombre") else valor


class TipoPaginado(BaseModel):
    """Respuesta del listado: {data, total, page, limit}."""
    data: List[TipoOut] = Field(description="Tipos de la página solicitada, ordenados por id.")
    total: int = Field(description="Cantidad total de tipos que cumplen el filtro (no solo los de esta página).",
                       examples=[1])
    page: int = Field(description="Página devuelta (empieza en 1).", examples=[1])
    limit: int = Field(description="Cantidad máxima de elementos por página.", examples=[10])
