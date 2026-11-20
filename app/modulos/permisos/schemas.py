# Esquemas de Permiso (entrada, salida y listado paginado)
from datetime import datetime
from typing import Annotated, List, Optional

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

# Nombre: se quitan los espacios al inicio y al final y luego debe tener de 1 a 100 caracteres
NombrePermiso = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]

# Descripción: se quitan los espacios y puede tener hasta 255 caracteres ("" se permite para borrarla)
DescripcionPermiso = Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)]


class PermisoCreate(BaseModel):
    """Datos para crear un permiso (los campos de auditoría los pone el servidor)."""
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"nombre": "crear_orden", "descripcion": "Puede crear órdenes", "estado": True}]
        }
    )

    nombre: NombrePermiso = Field(
        description="**Obligatorio.** Nombre del permiso, de 1 a 100 caracteres. "
                    "Se quitan los espacios al inicio y al final. "
                    "Debe ser único (sin distinguir mayúsculas).",
        examples=["crear_orden"],
    )
    descripcion: Optional[DescripcionPermiso] = Field(
        default=None,
        description="Opcional. Explicación de lo que permite, hasta 255 caracteres. Si no se envía, queda en `null`.",
        examples=["Puede crear órdenes"],
    )
    estado: bool = Field(
        default=True,
        description="Opcional. `true` = activo, `false` = inactivo. Si no se envía, queda activo.",
        examples=[True],
    )


class PermisoUpdate(BaseModel):
    """Datos para editar un permiso (todos opcionales; los de auditoría los pone el servidor)."""
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"descripcion": "Puede crear y editar órdenes", "estado": True}]}
    )

    nombre: Optional[NombrePermiso] = Field(
        default=None,
        description="Opcional. Nuevo nombre, de 1 a 100 caracteres, único (sin distinguir mayúsculas). "
                    "Si no se envía o llega en `null`, no se cambia.",
        examples=["editar_orden"],
    )
    descripcion: Optional[DescripcionPermiso] = Field(
        default=None,
        description='Opcional. Nueva descripción, hasta 255 caracteres. Para **borrarla** se envía `""` '
                    "(cadena vacía). Si no se envía o llega en `null`, no se cambia.",
        examples=["Puede crear y editar órdenes"],
    )
    estado: Optional[bool] = Field(
        default=None,
        description="Opcional. `true` activa y `false` desactiva el permiso. "
                    "Si no se envía o llega en `null`, no se cambia.",
        examples=[True],
    )


class PermisoOut(BaseModel):
    """Permiso tal como se devuelve al frontend."""
    model_config = ConfigDict(
        from_attributes=True,  # permite crearlo desde el modelo de SQLAlchemy
        json_schema_extra={
            "examples": [{
                "id": 1,
                "nombre": "crear_orden",
                "descripcion": "Puede crear órdenes",
                "estado": True,
                "creado_en": "2026-11-18T10:30:00",
                "actualizado_en": "2026-11-18T10:30:00",
                "creado_por": 1,
                "actualizado_por": 1,
            }]
        },
    )

    id: int = Field(description="Id del permiso (lo genera el servidor).", examples=[1])
    nombre: str = Field(description="Nombre del permiso.", examples=["crear_orden"])
    descripcion: Optional[str] = Field(default=None,
                                       description='Descripción del permiso. Puede venir en `null` (nunca se envió) '
                                                   'o `""` (se borró con PUT).',
                                       examples=["Puede crear órdenes"])
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


class PermisoPaginado(BaseModel):
    """Respuesta del listado: {data, total, page, limit}."""
    data: List[PermisoOut] = Field(description="Permisos de la página solicitada, ordenados por id.")
    total: int = Field(description="Cantidad total de permisos que cumplen el filtro (no solo los de esta página).",
                       examples=[1])
    page: int = Field(description="Página devuelta (empieza en 1).", examples=[1])
    limit: int = Field(description="Cantidad máxima de elementos por página.", examples=[10])
