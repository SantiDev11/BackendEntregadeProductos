# Esquemas de Rol (entrada, salida, asignación de permisos y listado paginado)
from datetime import datetime
from typing import Annotated, List, Optional

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.modulos.comun.validadores import Entero

# Nombre: se quitan los espacios al inicio y al final y luego debe tener de 1 a 50 caracteres
NombreRol = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]

# Descripción: se quitan los espacios y puede tener hasta 255 caracteres ("" se permite para borrarla)
DescripcionRol = Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)]


class PermisoResumen(BaseModel):
    """Datos básicos de un permiso asignado a un rol."""
    model_config = ConfigDict(
        from_attributes=True,  # permite crearlo desde el modelo de SQLAlchemy
        json_schema_extra={"examples": [{"id": 1, "nombre": "crear_orden"}]},
    )

    id: int = Field(description="Id del permiso.", examples=[1])
    nombre: str = Field(description="Nombre del permiso.", examples=["crear_orden"])


class RolCreate(BaseModel):
    """Datos para crear un rol (se crea sin permisos; los de auditoría los pone el servidor)."""
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"nombre": "supervisor", "descripcion": "Revisa órdenes", "estado": True}]
        }
    )

    nombre: NombreRol = Field(
        description="**Obligatorio.** Nombre del rol, de 1 a 50 caracteres. "
                    "Se quitan los espacios al inicio y al final. "
                    "Debe ser único (sin distinguir mayúsculas).",
        examples=["supervisor"],
    )
    descripcion: Optional[DescripcionRol] = Field(
        default=None,
        description="Opcional. Explicación del rol, hasta 255 caracteres. Si no se envía, queda en `null`.",
        examples=["Revisa órdenes"],
    )
    estado: bool = Field(
        default=True,
        description="Opcional. `true` = activo, `false` = inactivo. Si no se envía, queda activo.",
        examples=[True],
    )


class RolUpdate(BaseModel):
    """Datos para editar un rol (todos opcionales; los permisos se cambian con PUT /roles/{id}/permisos)."""
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"descripcion": "Revisa y aprueba órdenes", "estado": True}]}
    )

    nombre: Optional[NombreRol] = Field(
        default=None,
        description="Opcional. Nuevo nombre, de 1 a 50 caracteres, único (sin distinguir mayúsculas). "
                    "Si no se envía o llega en `null`, no se cambia.",
        examples=["supervisor_general"],
    )
    descripcion: Optional[DescripcionRol] = Field(
        default=None,
        description='Opcional. Nueva descripción, hasta 255 caracteres. Para **borrarla** se envía `""` '
                    "(cadena vacía). Si no se envía o llega en `null`, no se cambia.",
        examples=["Revisa y aprueba órdenes"],
    )
    estado: Optional[bool] = Field(
        default=None,
        description="Opcional. `true` activa y `false` desactiva el rol. "
                    "Si no se envía o llega en `null`, no se cambia.",
        examples=[True],
    )


class RolPermisosUpdate(BaseModel):
    """Lista completa de permisos que debe tener el rol (reemplaza la actual)."""
    model_config = ConfigDict(json_schema_extra={"examples": [{"permisos_ids": [1, 2, 3]}]})

    permisos_ids: List[Entero] = Field(
        description="**Obligatorio.** Ids de los permisos que tendrá el rol. **Reemplaza** todos los actuales. "
                    "Una lista vacía `[]` le quita todos. Los ids repetidos se ignoran.",
        examples=[[1, 2, 3]],
    )


class RolOut(BaseModel):
    """Rol tal como se devuelve al frontend, con sus permisos."""
    model_config = ConfigDict(
        from_attributes=True,  # permite crearlo desde el modelo de SQLAlchemy
        json_schema_extra={
            "examples": [{
                "id": 4,
                "nombre": "supervisor",
                "descripcion": "Revisa órdenes",
                "estado": True,
                "creado_en": "2026-11-18T10:30:00",
                "actualizado_en": "2026-11-18T10:30:00",
                "creado_por": 1,
                "actualizado_por": 1,
                "permisos": [{"id": 1, "nombre": "crear_orden"}],
            }]
        },
    )

    id: int = Field(description="Id del rol (lo genera el servidor).", examples=[4])
    nombre: str = Field(description="Nombre del rol.", examples=["supervisor"])
    descripcion: Optional[str] = Field(default=None,
                                       description='Descripción del rol. Puede venir en `null` (nunca se envió) '
                                                   'o `""` (se borró con PUT).',
                                       examples=["Revisa órdenes"])
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
    permisos: List[PermisoResumen] = Field(default_factory=list,
                                           description="Permisos asignados al rol (lista vacía si no tiene).")


class RolPaginado(BaseModel):
    """Respuesta del listado: {data, total, page, limit}."""
    data: List[RolOut] = Field(description="Roles de la página solicitada, ordenados por id, cada uno con sus permisos.")
    total: int = Field(description="Cantidad total de roles que cumplen el filtro (no solo los de esta página).",
                       examples=[3])
    page: int = Field(description="Página devuelta (empieza en 1).", examples=[1])
    limit: int = Field(description="Cantidad máxima de elementos por página.", examples=[10])
