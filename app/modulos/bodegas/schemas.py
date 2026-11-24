# Esquemas de Bodega (entrada, salida y listado paginado)
from datetime import datetime
from typing import Annotated, List, Optional

from pydantic import (AfterValidator, BaseModel, ConfigDict, EmailStr, Field, StringConstraints, TypeAdapter,
                      ValidationError, field_validator)
from pydantic_core import PydanticCustomError

from app.modulos.comun.validadores import DocumentoObligatorio, Entero, TelefonoObligatorio

# Todos los datos de la bodega son obligatorios: se quitan los espacios al inicio y al final
# y luego no pueden quedar vacíos (mínimo 1 carácter) ni pasarse del largo máximo.
NombreBodega = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
DireccionBodega = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Texto30 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)]
Texto100 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]

_validar_email = TypeAdapter(EmailStr)


def _correo_valido(valor: str) -> str:
    """Valida el formato del correo."""
    try:
        return _validar_email.validate_python(valor)
    except ValidationError:
        # mismo tipo y mensaje que EmailStr, así el manejador lo traduce a "formato de correo inválido"
        raise PydanticCustomError("value_error", "value is not a valid email address")


# Correo de la bodega: obligatorio, formato de correo válido, hasta 100 caracteres
CorreoBodega = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
    AfterValidator(_correo_valido),
]

# Ejemplo completo de una bodega con todos sus datos
EJEMPLO_DATOS = {
    "nombre": "Bodega Central",
    "codigo": "BOD-01",
    "direccion": "Calle 1 # 2-3",
    "ciudad": "Bogotá",
    "departamento": "Cundinamarca",
    "telefono": "6015551234",
    "correo": "central@entrega.com",
    "recibe_nombre": "Ana Ruiz",
    "recibe_documento": "52123456",
    "recibe_cargo": "Jefe de bodega",
    "recibe_telefono": "3001234567",
}

NO_VACIO = 'Si no se envía o llega en `null`, no se cambia. **No puede quedar vacío** (`""` da 422).'


class BodegaCreate(BaseModel):
    """Datos para crear una bodega. **Todos los datos son obligatorios** (salvo `bodeguero_id` y `estado`)."""
    model_config = ConfigDict(json_schema_extra={"examples": [{**EJEMPLO_DATOS, "estado": True}]})

    nombre: NombreBodega = Field(
        description="**Obligatorio.** Nombre de la bodega, de 1 a 100 caracteres. Debe ser único (sin distinguir mayúsculas).",
        examples=["Bodega Central"],
    )
    codigo: Texto30 = Field(
        description="**Obligatorio.** Código interno, hasta 30 caracteres. Se guarda en **mayúsculas** "
                    "y debe ser único (sin distinguir mayúsculas).",
        examples=["BOD-01"],
    )
    direccion: DireccionBodega = Field(description="**Obligatorio.** Dirección de la bodega, hasta 200 caracteres.",
                                       examples=["Calle 1 # 2-3"])
    ciudad: Texto100 = Field(description="**Obligatorio.** Ciudad, hasta 100 caracteres.", examples=["Bogotá"])
    departamento: Texto100 = Field(description="**Obligatorio.** Departamento, hasta 100 caracteres.",
                                   examples=["Cundinamarca"])
    telefono: TelefonoObligatorio = Field(description="**Obligatorio.** Teléfono de la bodega: **solo números**, de 7 a 15 dígitos.",
                                          examples=["6015551234"])
    correo: CorreoBodega = Field(description="**Obligatorio.** Correo de la bodega, con formato válido (hasta 100 caracteres).",
                                 examples=["central@entrega.com"])
    recibe_nombre: Texto100 = Field(description="**Obligatorio.** Nombre de la persona que recibe la mercancía, hasta 100 caracteres.",
                                    examples=["Ana Ruiz"])
    recibe_documento: DocumentoObligatorio = Field(description="**Obligatorio.** Documento de quien recibe: **solo números**, "
                                                               "hasta 30 dígitos.",
                                                   examples=["52123456"])
    recibe_cargo: Texto100 = Field(description="**Obligatorio.** Cargo de quien recibe, hasta 100 caracteres.",
                                   examples=["Jefe de bodega"])
    recibe_telefono: TelefonoObligatorio = Field(description="**Obligatorio.** Teléfono de quien recibe: **solo números**, "
                                                             "de 7 a 15 dígitos.",
                                                 examples=["3001234567"])
    bodeguero_id: Optional[Entero] = Field(
        default=None,
        description="Opcional, **solo para admin**. Id del bodeguero dueño de la bodega. "
                    "Si la crea un bodeguero, el dueño es él mismo y este campo se ignora.",
        examples=[2],
    )
    estado: bool = Field(
        default=True,
        description="Opcional. `true` = activa, `false` = inactiva. Si no se envía, queda activa.",
        examples=[True],
    )


class BodegaUpdate(BaseModel):
    """Datos para editar una bodega: se envían solo los que cambian, pero ninguno puede quedar vacío."""
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"recibe_nombre": "Ana Ruiz", "recibe_telefono": "3001234567"}]}
    )

    nombre: Optional[NombreBodega] = Field(default=None,
                                           description="Nuevo nombre, de 1 a 100 caracteres, único. " + NO_VACIO,
                                           examples=["Bodega Norte"])
    codigo: Optional[Texto30] = Field(default=None,
                                      description="Nuevo código, hasta 30 caracteres, en mayúsculas y único. " + NO_VACIO,
                                      examples=["BOD-02"])
    direccion: Optional[DireccionBodega] = Field(default=None, description="Nueva dirección, hasta 200 caracteres. " + NO_VACIO,
                                                 examples=["Carrera 7 # 10-20"])
    ciudad: Optional[Texto100] = Field(default=None, description="Ciudad. " + NO_VACIO, examples=["Medellín"])
    departamento: Optional[Texto100] = Field(default=None, description="Departamento. " + NO_VACIO, examples=["Antioquia"])
    telefono: Optional[TelefonoObligatorio] = Field(default=None,
                                                    description="Teléfono de la bodega: **solo números**, de 7 a 15 dígitos. "
                                                                + NO_VACIO,
                                                    examples=["6045551234"])
    correo: Optional[CorreoBodega] = Field(default=None, description="Correo de la bodega, con formato válido. " + NO_VACIO,
                                           examples=["norte@entrega.com"])
    recibe_nombre: Optional[Texto100] = Field(default=None, description="Nombre de quien recibe. " + NO_VACIO,
                                              examples=["Ana Ruiz"])
    recibe_documento: Optional[DocumentoObligatorio] = Field(default=None,
                                                             description="Documento de quien recibe: **solo números**. " + NO_VACIO,
                                                             examples=["52123456"])
    recibe_cargo: Optional[Texto100] = Field(default=None, description="Cargo de quien recibe. " + NO_VACIO,
                                             examples=["Jefe de bodega"])
    recibe_telefono: Optional[TelefonoObligatorio] = Field(default=None,
                                                           description="Teléfono de quien recibe: **solo números**, "
                                                                       "de 7 a 15 dígitos. " + NO_VACIO,
                                                           examples=["3001234567"])
    bodeguero_id: Optional[Entero] = Field(
        default=None,
        description="Opcional, **solo para admin**. Nuevo bodeguero dueño. Si lo envía un bodeguero, se ignora "
                    "(no puede pasarle su bodega a otro).",
        examples=[2],
    )
    estado: Optional[bool] = Field(
        default=None,
        description="Opcional. `true` activa y `false` desactiva la bodega. "
                    "Si no se envía o llega en `null`, no se cambia.",
        examples=[True],
    )


class BodegaOut(BaseModel):
    """Bodega tal como se devuelve al frontend."""
    model_config = ConfigDict(
        from_attributes=True,  # permite crearlo desde el modelo de SQLAlchemy
        json_schema_extra={
            "examples": [{
                "id": 1,
                **EJEMPLO_DATOS,
                "bodeguero_id": 2,
                "bodeguero_nombre": "Bodeguero Prueba",
                "estado": True,
                "creado_en": "2026-11-18T10:30:00",
                "actualizado_en": "2026-11-18T10:30:00",
                "creado_por": 1,
                "actualizado_por": 1,
            }]
        },
    )

    id: int = Field(description="Id de la bodega (lo genera el servidor).", examples=[1])
    nombre: str = Field(description="Nombre de la bodega.", examples=["Bodega Central"])
    codigo: Optional[str] = Field(default=None, description="Código interno en mayúsculas, o `null`.", examples=["BOD-01"])
    direccion: Optional[str] = Field(default=None, description="Dirección de la bodega, o `null`.", examples=["Calle 1 # 2-3"])
    ciudad: Optional[str] = Field(default=None, description="Ciudad, o `null`.", examples=["Bogotá"])
    departamento: Optional[str] = Field(default=None, description="Departamento, o `null`.", examples=["Cundinamarca"])
    telefono: Optional[str] = Field(default=None, description="Teléfono de la bodega, o `null`.", examples=["6015551234"])
    correo: Optional[str] = Field(default=None, description="Correo de la bodega, o `null`.", examples=["central@entrega.com"])
    recibe_nombre: Optional[str] = Field(default=None, description="Nombre de quien recibe, o `null`.", examples=["Ana Ruiz"])
    recibe_documento: Optional[str] = Field(default=None, description="Documento de quien recibe, o `null`.", examples=["52123456"])
    recibe_cargo: Optional[str] = Field(default=None, description="Cargo de quien recibe, o `null`.", examples=["Jefe de bodega"])
    recibe_telefono: Optional[str] = Field(default=None, description="Teléfono de quien recibe, o `null`.", examples=["3001234567"])
    bodeguero_id: Optional[int] = Field(default=None, description="Id del bodeguero dueño, o `null` si no tiene.", examples=[2])
    bodeguero_nombre: Optional[str] = Field(default=None, validation_alias="bodeguero",
                                            description="Nombre del bodeguero dueño, o `null`.", examples=["Bodeguero Prueba"])
    estado: bool = Field(description="`true` = activa, `false` = inactiva.", examples=[True])
    creado_en: datetime = Field(description="Fecha y hora de creación (la pone el servidor).",
                                examples=["2026-11-18T10:30:00"])
    actualizado_en: datetime = Field(description="Fecha y hora de la última modificación (la pone el servidor).",
                                     examples=["2026-11-18T10:30:00"])
    creado_por: Optional[int] = Field(default=None,
                                      description="Id del usuario que la creó (lo pone el servidor).",
                                      examples=[1])
    actualizado_por: Optional[int] = Field(default=None,
                                           description="Id del usuario que la modificó por última vez (lo pone el servidor).",
                                           examples=[1])

    @field_validator("bodeguero_nombre", mode="before")
    @classmethod
    def nombre_del_bodeguero(cls, valor):
        """El modelo entrega el objeto Usuario (relación "bodeguero"); aquí se convierte en su nombre."""
        return valor.nombre if hasattr(valor, "nombre") else valor


class BodegaPaginado(BaseModel):
    """Respuesta del listado: {data, total, page, limit}."""
    data: List[BodegaOut] = Field(description="Bodegas de la página solicitada, ordenadas por id.")
    total: int = Field(description="Cantidad total de bodegas que cumplen el filtro (no solo las de esta página).",
                       examples=[1])
    page: int = Field(description="Página devuelta (empieza en 1).", examples=[1])
    limit: int = Field(description="Cantidad máxima de elementos por página.", examples=[10])
