# Esquemas del registro público. `tipo` decide cuál se usa: cliente o empresa.
# El rol, el estado y los permisos los pone el servidor: si llegan en el cuerpo, se ignoran.
from typing import Annotated, Literal, Union

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field, StringConstraints, WithJsonSchema
from pydantic_core import PydanticCustomError

from app.modulos.empresas.schemas import EmpresaCreate
from app.modulos.usuarios.schemas import Contrasena, NombreUsuario, TipoDocumento

MSG_SOLO_NUMEROS = "solo puede tener números"
MSG_TELEFONO_LARGO = "debe tener entre 7 y 15 dígitos"
MSG_DOCUMENTO = "solo puede tener letras y números"


def _validar_telefono(valor: str) -> str:
    """Solo dígitos (0-9), de 7 a 15."""
    if not (valor.isascii() and valor.isdigit()):
        raise PydanticCustomError("solo_numeros", MSG_SOLO_NUMEROS)
    if not 7 <= len(valor) <= 15:
        raise PydanticCustomError("telefono_largo", MSG_TELEFONO_LARGO)
    return valor


def _validar_documento(valor: str) -> str:
    """Letras (sin tildes ni ñ) y números: los documentos extranjeros pueden llevar letras. Sin espacios ni símbolos."""
    if not (valor.isascii() and valor.isalnum()):
        raise PydanticCustomError("documento", MSG_DOCUMENTO)
    return valor


def _correo_hasta_100(valor: str) -> str:
    if len(valor) > 100:
        raise PydanticCustomError("string_too_long", "es demasiado largo")  # lo que cabe en la base
    return valor.lower()  # el correo siempre se guarda en minúsculas


def _no_vacio(valor: str) -> str:
    if valor == "":
        raise PydanticCustomError("vacio", "no puede estar vacío")
    return valor


# Teléfono: se guarda como texto (puede empezar en 0), pero solo con dígitos. No puede quedar vacío
TelefonoObligatorio = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1), AfterValidator(_validar_telefono),
                                WithJsonSchema({"type": "string", "pattern": "^[0-9]{7,15}$"})]

# Documento: texto con letras y números, hasta 30. No puede quedar vacío
DocumentoObligatorio = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30),
                                 AfterValidator(_validar_documento),
                                 WithJsonSchema({"type": "string", "pattern": "^[A-Za-z0-9]{1,30}$"})]

Correo = Annotated[EmailStr, AfterValidator(_correo_hasta_100)]


class RegistroCliente(BaseModel):
    """Registro de un cliente: queda activo de inmediato."""
    model_config = ConfigDict(json_schema_extra={"examples": [{
        "tipo": "cliente", "nombre": "Juan Pérez", "tipo_documento": "CC", "numero_documento": "1020304050",
        "telefono": "3001234567", "correo": "juan@cliente.com", "contrasena": "Cliente123*"}]})

    tipo: Literal["cliente"]
    nombre: NombreUsuario = Field(description="**Obligatorio.** De 1 a 100 caracteres.", examples=["Juan Pérez"])
    tipo_documento: Annotated[TipoDocumento, AfterValidator(_no_vacio)] = Field(
        description="**Obligatorio.** `CC`, `NIT`, `CE` o `PA`.", examples=["CC"])
    numero_documento: DocumentoObligatorio = Field(
        description="**Obligatorio.** Letras y números, hasta 30. Debe ser único (sin distinguir mayúsculas).", examples=["1020304050"])
    telefono: TelefonoObligatorio = Field(description="**Obligatorio.** Solo números, de 7 a 15 dígitos.", examples=["3001234567"])
    correo: Correo = Field(description="**Obligatorio.** Formato de correo, hasta 100 caracteres. Debe ser único.",
                           examples=["juan@cliente.com"])
    contrasena: Contrasena = Field(description="**Obligatorio.** De 8 a 72 caracteres.", examples=["Cliente123*"])


class RegistroEmpresa(EmpresaCreate):
    """Registro de una empresa: los mismos datos que pide el admin al crearla, pero queda pendiente hasta que la aprueben.
    También crea su usuario."""
    model_config = ConfigDict(json_schema_extra={"examples": [{
        "tipo": "empresa", "razon_social": "Distribuidora Andina S.A.S.", "nit": "900123456-1", "telefono": "3001234567",
        "direccion": "Calle 10 # 20-30", "representante": "Ana Torres", "correo": "empresa@entrega.com",
        "contrasena": "Empresa123*"}]})

    tipo: Literal["empresa"]


Registro = Annotated[Union[RegistroCliente, RegistroEmpresa], Field(discriminator="tipo")]


# ===== SALIDA =====

class UsuarioRegistrado(BaseModel):
    id: int = Field(examples=[9])
    nombre: str = Field(examples=["Juan Pérez"])
    correo: str = Field(examples=["juan@cliente.com"])
    rol: str = Field(examples=["cliente"])


class RegistroClienteOut(BaseModel):
    message: str = Field(examples=["Cuenta creada"])
    user: UsuarioRegistrado


class EmpresaRegistrada(BaseModel):
    id: int = Field(examples=[1])
    razon_social: str = Field(examples=["Distribuidora Andina S.A.S."])
    nit: str = Field(examples=["900123456-1"])
    estado: str = Field(examples=["pendiente"])


class RegistroEmpresaOut(BaseModel):
    message: str = Field(examples=["Registro recibido. Un administrador debe aprobar la empresa"])
    estado: str = Field(examples=["pendiente"])
    empresa: EmpresaRegistrada
