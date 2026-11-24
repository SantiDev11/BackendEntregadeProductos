# Esquemas de Usuario (entrada, salida y listado paginado). La contraseña nunca se devuelve.
from datetime import datetime
from typing import Annotated, List, Optional

from pydantic import (AfterValidator, BaseModel, BeforeValidator, ConfigDict, EmailStr, Field,
                      StringConstraints, ValidationInfo, field_validator)
from pydantic_core import PydanticCustomError

from app.modulos.comun.validadores import Entero, Telefono, error_documento
from app.modulos.roles.schemas import PermisoResumen  # {id, nombre} de cada permiso

# Nombre: se quitan los espacios al inicio y al final y luego debe tener de 1 a 100 caracteres
NombreUsuario = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]

# Contraseña: de 8 a 72 caracteres (72 es el límite de bcrypt). No se quitan espacios: se respeta tal cual.
Contrasena = Annotated[str, StringConstraints(min_length=8, max_length=72)]

# Textos opcionales de facturación: se quitan los espacios; "" se permite para borrar el campo
Texto30 = Annotated[str, StringConstraints(strip_whitespace=True, max_length=30)]
Texto100 = Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)]
Texto200 = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]

# Tipos de documento permitidos
TIPOS_DOCUMENTO = ("CC", "NIT", "CE", "PA")


def _normalizar_tipo_documento(valor):
    """Quita espacios y pasa a mayúsculas ("cc" -> "CC") antes de validar."""
    return valor.strip().upper() if isinstance(valor, str) else valor


def _validar_tipo_documento(valor: str) -> str:
    """Solo acepta CC, NIT, CE, PA o "" (para borrarlo)."""
    if valor not in TIPOS_DOCUMENTO and valor != "":
        raise PydanticCustomError("tipo_documento", "debe ser CC, NIT, CE o PA")
    return valor


# Tipo de documento: CC, NIT, CE o PA (sin distinguir mayúsculas), o "" para borrarlo
TipoDocumento = Annotated[
    str,
    BeforeValidator(_normalizar_tipo_documento),
    AfterValidator(_validar_tipo_documento),
]

TEXTO_BORRAR = 'Para **borrarlo** se envía `""` (se guarda como `null`).'


class UsuarioCreate(BaseModel):
    """Datos para crear un usuario (los campos de auditoría los pone el servidor)."""
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{
                "nombre": "Cliente Prueba",
                "correo": "cliente@entrega.com",
                "contrasena": "Cliente123*",
                "rol_id": 3,
                "tipo_documento": "CC",
                "numero_documento": "1020304050",
                "telefono": "3001234567",
                "direccion": "Calle 10 # 20-30",
                "ciudad": "Bogotá",
                "estado": True,
            }]
        }
    )

    nombre: NombreUsuario = Field(
        description="**Obligatorio.** Nombre del usuario, de 1 a 100 caracteres. "
                    "Se quitan los espacios al inicio y al final.",
        examples=["Cliente Prueba"],
    )
    correo: EmailStr = Field(
        description="**Obligatorio.** Correo con formato válido. Se guarda en **minúsculas** "
                    "y debe ser único (sin distinguir mayúsculas).",
        examples=["cliente@entrega.com"],
    )
    contrasena: Contrasena = Field(
        description="**Obligatorio.** Contraseña de 8 a 72 caracteres. Se guarda cifrada (bcrypt) y **nunca** se devuelve.",
        examples=["Cliente123*"],
    )
    rol_id: Entero = Field(
        description="**Obligatorio.** Id de un rol existente (consulta `GET /roles`). Debe ser un número, no un texto.",
        examples=[3],
    )
    tipo_documento: Optional[TipoDocumento] = Field(
        default=None,
        description="Opcional. Tipo de documento: `CC`, `NIT`, `CE` o `PA` (se acepta en minúsculas y se guarda en mayúsculas).",
        examples=["CC"],
    )
    numero_documento: Optional[Texto30] = Field(
        default=None,
        description="Opcional. Número de documento, hasta 30 caracteres. Debe ser único. **Solo números**; "
                    "si el tipo es `PA` (pasaporte) también acepta letras.",
        examples=["1020304050"],
    )
    telefono: Optional[Telefono] = Field(default=None, description="Opcional. Teléfono: **solo números**, de 7 a 15 dígitos.",
                                         examples=["3001234567"])
    direccion: Optional[Texto200] = Field(default=None, description="Opcional. Dirección, hasta 200 caracteres.",
                                          examples=["Calle 10 # 20-30"])
    ciudad: Optional[Texto100] = Field(default=None, description="Opcional. Ciudad, hasta 100 caracteres.",
                                       examples=["Bogotá"])
    estado: bool = Field(
        default=True,
        description="Opcional. `true` = activo, `false` = inactivo (no puede iniciar sesión). Si no se envía, queda activo.",
        examples=[True],
    )

    @field_validator("numero_documento", mode="after")
    @classmethod
    def documento_segun_tipo(cls, valor, info: ValidationInfo):
        """Solo números (o letras y números si es pasaporte). Si el tipo vino mal, ya hay un error por el tipo."""
        mensaje = error_documento(info.data["tipo_documento"], valor) if "tipo_documento" in info.data else None
        if mensaje:
            raise PydanticCustomError("documento", mensaje)
        return valor


class UsuarioUpdate(BaseModel):
    """Datos para editar un usuario (todos opcionales; los de auditoría los pone el servidor)."""
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"nombre": "Cliente Editado", "telefono": "3109876543"}]}
    )

    nombre: Optional[NombreUsuario] = Field(
        default=None,
        description="Opcional. Nuevo nombre, de 1 a 100 caracteres. Si no se envía o llega en `null`, no se cambia.",
        examples=["Cliente Editado"],
    )
    correo: Optional[EmailStr] = Field(
        default=None,
        description="Opcional. Nuevo correo; se guarda en minúsculas y no puede tenerlo **otro** usuario. "
                    "Si no se envía o llega en `null`, no se cambia.",
        examples=["cliente.nuevo@entrega.com"],
    )
    contrasena: Optional[Contrasena] = Field(
        default=None,
        description="Opcional. Nueva contraseña, de 8 a 72 caracteres. "
                    "Si no se envía o llega en `null`, la contraseña actual **no** se toca.",
        examples=["NuevaClave1*"],
    )
    rol_id: Optional[Entero] = Field(
        default=None,
        description="Opcional. Id de un rol existente. Si no se envía o llega en `null`, no se cambia.",
        examples=[3],
    )
    tipo_documento: Optional[TipoDocumento] = Field(
        default=None,
        description="Opcional. `CC`, `NIT`, `CE` o `PA`. " + TEXTO_BORRAR,
        examples=["CC"],
    )
    numero_documento: Optional[Texto30] = Field(
        default=None,
        description="Opcional. Número de documento; no puede tenerlo **otro** usuario. **Solo números**; "
                    "si el tipo es `PA` (pasaporte) también acepta letras. " + TEXTO_BORRAR,
        examples=["1020304050"],
    )
    telefono: Optional[Telefono] = Field(default=None,
                                         description="Opcional. Teléfono: **solo números**, de 7 a 15 dígitos. " + TEXTO_BORRAR,
                                         examples=["3109876543"])
    direccion: Optional[Texto200] = Field(default=None, description="Opcional. Dirección. " + TEXTO_BORRAR,
                                          examples=["Carrera 5 # 6-7"])
    ciudad: Optional[Texto100] = Field(default=None, description="Opcional. Ciudad. " + TEXTO_BORRAR,
                                       examples=["Medellín"])
    estado: Optional[bool] = Field(
        default=None,
        description="Opcional. `true` activa y `false` desactiva el usuario (un inactivo no puede iniciar sesión). "
                    "Si no se envía o llega en `null`, no se cambia.",
        examples=[True],
    )


class UsuarioOut(BaseModel):
    """Usuario tal como se devuelve al frontend. Nunca incluye la contraseña ni su hash."""
    model_config = ConfigDict(
        from_attributes=True,  # permite crearlo desde el modelo de SQLAlchemy
        json_schema_extra={
            "examples": [{
                "id": 3,
                "nombre": "Cliente Prueba",
                "correo": "cliente@entrega.com",
                "rol_id": 3,
                "rol": "cliente",
                "tipo_documento": "CC",
                "numero_documento": "1020304050",
                "telefono": "3001234567",
                "direccion": "Calle 10 # 20-30",
                "ciudad": "Bogotá",
                "estado": True,
                "creado_en": "2026-11-18T10:30:00",
                "actualizado_en": "2026-11-18T10:30:00",
                "creado_por": 1,
                "actualizado_por": 1,
                "permisos": [{"id": 1, "nombre": "ver_facturas"}],
            }]
        },
    )

    id: int = Field(description="Id del usuario (lo genera el servidor).", examples=[3])
    nombre: str = Field(description="Nombre del usuario.", examples=["Cliente Prueba"])
    correo: str = Field(description="Correo del usuario, en minúsculas.", examples=["cliente@entrega.com"])
    rol_id: int = Field(description="Id del rol del usuario.", examples=[3])
    rol: str = Field(description="Nombre del rol como texto: `admin`, `bodeguero`, `cliente`, etc.", examples=["cliente"])
    tipo_documento: Optional[str] = Field(default=None, description="Tipo de documento (`CC`, `NIT`, `CE`, `PA`), o `null`.",
                                          examples=["CC"])
    numero_documento: Optional[str] = Field(default=None, description="Número de documento, o `null`.", examples=["1020304050"])
    telefono: Optional[str] = Field(default=None, description="Teléfono, o `null`.", examples=["3001234567"])
    direccion: Optional[str] = Field(default=None, description="Dirección, o `null`.", examples=["Calle 10 # 20-30"])
    ciudad: Optional[str] = Field(default=None, description="Ciudad, o `null`.", examples=["Bogotá"])
    estado: bool = Field(description="`true` = activo, `false` = inactivo (no puede iniciar sesión).", examples=[True])
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
                                           description="Permisos efectivos del usuario (lista vacía si no tiene).")

    @field_validator("rol", mode="before")
    @classmethod
    def rol_como_texto(cls, valor):
        """El modelo entrega el objeto Rol; aquí se convierte en su nombre ("cliente")."""
        return valor.nombre if hasattr(valor, "nombre") else valor


class UsuarioPaginado(BaseModel):
    """Respuesta del listado: {data, total, page, limit}."""
    data: List[UsuarioOut] = Field(description="Usuarios de la página solicitada, ordenados por id.")
    total: int = Field(description="Cantidad total de usuarios que cumplen los filtros (no solo los de esta página).",
                       examples=[3])
    page: int = Field(description="Página devuelta (empieza en 1).", examples=[1])
    limit: int = Field(description="Cantidad máxima de elementos por página.", examples=[10])


class UsuarioPermisosOut(BaseModel):
    """Respuesta de GET /usuarios/{id}/permisos: {data: [{id, nombre}]}."""
    data: List[PermisoResumen] = Field(description="Permisos efectivos del usuario, ordenados por id.")


class UsuarioPermisosUpdate(BaseModel):
    """Lista completa de permisos que debe tener el usuario (reemplaza la actual)."""
    model_config = ConfigDict(json_schema_extra={"examples": [{"permisos_ids": [1, 2]}]})

    permisos_ids: List[Entero] = Field(
        description="**Obligatorio.** Ids de los permisos que tendrá el usuario. **Reemplaza** todos los actuales. "
                    "Una lista vacía `[]` le quita todos. Los ids repetidos se ignoran.",
        examples=[[1, 2]],
    )
