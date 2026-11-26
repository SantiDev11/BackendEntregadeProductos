# Esquemas de Tipo (entrada, salida y listado paginado)
from datetime import datetime
from typing import Annotated, List, Optional

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints, field_validator
from pydantic_core import PydanticCustomError

MSG_NUMERO = "debe ser un número"


def _exigir_numero(valor):
    """Solo deja pasar números del JSON (10). Rechaza textos ("10"), true/false y listas.
    null sigue su curso normal: lo permite o lo rechaza el propio campo."""
    if valor is not None and (isinstance(valor, bool) or not isinstance(valor, (int, float))):
        raise PydanticCustomError("no_es_numero", MSG_NUMERO)
    return valor


# Id enviado como número en el JSON: 3, no "3"
Entero = Annotated[int, BeforeValidator(_exigir_numero)]

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
                "empresa_id": 1,
                "empresa_nombre": "Distribuidora Andina S.A.S.",
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
    empresa_id: Optional[int] = Field(default=None, description="Empresa a la que pertenece el tipo, o `null` si no tiene.",
                                      examples=[1])
    empresa_nombre: Optional[str] = Field(default=None, validation_alias="empresa",
                                          description="Razón social de su empresa, o `null` si no tiene.",
                                          examples=["Distribuidora Andina S.A.S."])
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

    @field_validator("empresa_nombre", mode="before")
    @classmethod
    def nombre_de_la_empresa(cls, valor):
        """El modelo entrega el objeto Empresa (relación "empresa"); aquí se convierte en su razón social."""
        return valor.razon_social if hasattr(valor, "razon_social") else valor

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


# ===== ACTIVAR / DESACTIVAR (PATCH /{id}/estado) =====

MSG_BOOLEANO = "debe ser true o false"


def _exigir_booleano(valor):
    """Solo deja pasar true o false del JSON. Rechaza "true", 1, "si" y null."""
    if not isinstance(valor, bool):
        raise PydanticCustomError("no_es_booleano", MSG_BOOLEANO)
    return valor


Booleano = Annotated[bool, BeforeValidator(_exigir_booleano)]


class TipoEstadoUpdate(BaseModel):
    """Activa o desactiva el tipo."""
    model_config = ConfigDict(json_schema_extra={"examples": [{"estado": False}, {"estado": True}]})

    estado: Booleano = Field(description="**Obligatorio.** `true` activa y `false` desactiva el tipo. Inactivo (por ejemplo, sin stock) no se puede usar en facturas nuevas.",
                             examples=[False])
