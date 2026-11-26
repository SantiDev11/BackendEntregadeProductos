# Esquemas de Usuario (entrada, salida y listado paginado). La contraseña nunca se devuelve.
from datetime import datetime
from typing import Annotated, Any, List, Optional

from pydantic import (AfterValidator, BaseModel, BeforeValidator, ConfigDict, EmailStr, Field, StringConstraints,
                      WithJsonSchema, field_validator)
from pydantic_core import PydanticCustomError

from app.modulos.roles.schemas import PermisoResumen  # {id, nombre} de cada permiso

MSG_SOLO_NUMEROS = "solo puede tener números"
MSG_TELEFONO_LARGO = "debe tener entre 7 y 15 dígitos"
MSG_DOCUMENTO = "solo puede tener letras y números"
MSG_NUMERO = "debe ser un número"


def _exigir_numero(valor):
    """Solo deja pasar números del JSON (10). Rechaza textos ("10"), true/false y listas.
    null sigue su curso normal: lo permite o lo rechaza el propio campo."""
    if valor is not None and (isinstance(valor, bool) or not isinstance(valor, (int, float))):
        raise PydanticCustomError("no_es_numero", MSG_NUMERO)
    return valor


# Id enviado como número en el JSON: 3, no "3"
Entero = Annotated[int, BeforeValidator(_exigir_numero)]

# empresa_id: el schema lo acepta como venga, porque solo se tiene en cuenta si quien lo envía es admin
# (ahí lo valida validate_empresa_id); a los demás se les ignora, aunque llegue mal escrito
EmpresaIdDelBody = Annotated[Any, WithJsonSchema({"anyOf": [{"type": "integer"}, {"type": "null"}]})]


def _validar_telefono(valor: str) -> str:
    """Solo dígitos (0-9), de 7 a 15. Se permite "" (sirve para borrar el teléfono)."""
    if valor == "":
        return valor
    if not (valor.isascii() and valor.isdigit()):
        raise PydanticCustomError("solo_numeros", MSG_SOLO_NUMEROS)
    if not 7 <= len(valor) <= 15:
        raise PydanticCustomError("telefono_largo", MSG_TELEFONO_LARGO)
    return valor


def _validar_documento(valor: str) -> str:
    """Letras (sin tildes ni ñ) y números: los documentos extranjeros pueden llevar letras. Sin espacios ni símbolos.
    Se permite "" (sirve para borrar el documento)."""
    if valor and not (valor.isascii() and valor.isalnum()):
        raise PydanticCustomError("documento", MSG_DOCUMENTO)
    return valor


# Teléfono: se guarda como texto (puede empezar en 0), pero solo con dígitos
Telefono = Annotated[str, StringConstraints(strip_whitespace=True), AfterValidator(_validar_telefono),
                     WithJsonSchema({"type": "string", "pattern": "^([0-9]{7,15})?$"})]

# Documento: texto con letras y números, hasta 30, sin importar el tipo de documento
Documento = Annotated[str, StringConstraints(strip_whitespace=True, max_length=30), AfterValidator(_validar_documento),
                      WithJsonSchema({"type": "string", "pattern": "^[A-Za-z0-9]{0,30}$"})]

# Nombre: se quitan los espacios al inicio y al final y luego debe tener de 1 a 100 caracteres
NombreUsuario = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]

# Contraseña: de 8 a 72 caracteres (72 es el límite de bcrypt). No se quitan espacios: se respeta tal cual.
Contrasena = Annotated[str, StringConstraints(min_length=8, max_length=72)]

# Textos opcionales de facturación: se quitan los espacios; "" se permite para borrar el campo
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
    rol_id: Optional[Entero] = Field(
        default=None,
        description="**Obligatorio** (solo una empresa lo puede omitir: se asigna bodeguero). Id de un rol existente "
                    "(consulta `GET /roles`). Debe ser un número, no un texto.",
        examples=[3],
    )
    empresa_id: EmpresaIdDelBody = Field(
        default=None,
        description="**Obligatorio si el admin crea un bodeguero o un usuario empresa.** Id numérico de una empresa activa "
                    "(ver `GET /empresas?estado=activa`). En los demás roles, o si no lo envía el admin, se **ignora**: "
                    "lo que crea una empresa queda en la empresa del token.",
        examples=[1],
    )
    tipo_documento: Optional[TipoDocumento] = Field(
        default=None,
        description="Opcional. Tipo de documento: `CC`, `NIT`, `CE` o `PA` (se acepta en minúsculas y se guarda en mayúsculas).",
        examples=["CC"],
    )
    numero_documento: Optional[Documento] = Field(
        default=None,
        description="Opcional. Número de documento: **letras y números**, hasta 30 caracteres. Debe ser único (sin distinguir mayúsculas).",
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
    empresa_id: EmpresaIdDelBody = Field(
        default=None,
        description="**Obligatorio solo si el admin le cambia el rol a bodeguero o empresa y el usuario no tiene empresa.** "
                    "Id numérico de una empresa activa. En cualquier otro caso se **ignora**: la empresa no se edita.",
        examples=[1],
    )
    tipo_documento: Optional[TipoDocumento] = Field(
        default=None,
        description="Opcional. `CC`, `NIT`, `CE` o `PA`. " + TEXTO_BORRAR,
        examples=["CC"],
    )
    numero_documento: Optional[Documento] = Field(
        default=None,
        description="Opcional. Número de documento: **letras y números**; no puede tenerlo **otro** usuario. " + TEXTO_BORRAR,
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
                "empresa_id": 1,
                "empresa_nombre": "Distribuidora Andina S.A.S.",
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
    empresa_id: Optional[int] = Field(default=None, description="Empresa a la que pertenece el usuario, o `null` si no tiene.",
                                      examples=[1])
    empresa_nombre: Optional[str] = Field(default=None, validation_alias="empresa",
                                          description="Razón social de su empresa, o `null` si no tiene.",
                                          examples=["Distribuidora Andina S.A.S."])
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

    @field_validator("empresa_nombre", mode="before")
    @classmethod
    def nombre_de_la_empresa(cls, valor):
        """El modelo entrega el objeto Empresa (relación "empresa"); aquí se convierte en su razón social."""
        return valor.razon_social if hasattr(valor, "razon_social") else valor

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


# ===== ACTIVAR / DESACTIVAR (PATCH /{id}/estado) =====

MSG_BOOLEANO = "debe ser true o false"


def _exigir_booleano(valor):
    """Solo deja pasar true o false del JSON. Rechaza "true", 1, "si" y null."""
    if not isinstance(valor, bool):
        raise PydanticCustomError("no_es_booleano", MSG_BOOLEANO)
    return valor


Booleano = Annotated[bool, BeforeValidator(_exigir_booleano)]


class UsuarioEstadoUpdate(BaseModel):
    """Activa o desactiva el usuario."""
    model_config = ConfigDict(json_schema_extra={"examples": [{"estado": False}, {"estado": True}]})

    estado: Booleano = Field(description="**Obligatorio.** `true` activa y `false` desactiva el usuario. Inactivo no puede iniciar sesión y su token deja de funcionar.",
                             examples=[False])
