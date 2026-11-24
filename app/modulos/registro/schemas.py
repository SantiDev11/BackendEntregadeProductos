# Esquemas del registro público. `tipo` decide cuál se usa: cliente o empresa.
# El rol, el estado y los permisos los pone el servidor: si llegan en el cuerpo, se ignoran.
import re
from typing import Annotated, Literal, Union

from pydantic import (AfterValidator, BaseModel, ConfigDict, EmailStr, Field, StringConstraints, ValidationInfo,
                      field_validator)
from pydantic_core import PydanticCustomError

from app.modulos.comun.validadores import TelefonoObligatorio, error_documento
from app.modulos.usuarios.schemas import Contrasena, NombreUsuario, TipoDocumento

MSG_NIT = "debe tener el formato 900123456-1"
Texto100 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Texto200 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Documento = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)]


def _correo_hasta_100(valor: str) -> str:
    if len(valor) > 100:
        raise PydanticCustomError("string_too_long", "es demasiado largo")  # lo que cabe en la base
    return valor.lower()  # el correo siempre se guarda en minúsculas


def _no_vacio(valor: str) -> str:
    if valor == "":
        raise PydanticCustomError("vacio", "no puede estar vacío")
    return valor


def _validar_nit(valor: str) -> str:
    """900123456-1: de 5 a 15 dígitos, guion y dígito de verificación."""
    if not re.fullmatch(r"[0-9]{5,15}-[0-9]", valor):
        raise PydanticCustomError("nit", MSG_NIT)
    return valor


Correo = Annotated[EmailStr, AfterValidator(_correo_hasta_100)]
Nit = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1), AfterValidator(_validar_nit)]


class RegistroCliente(BaseModel):
    """Registro de un cliente: queda activo de inmediato."""
    model_config = ConfigDict(json_schema_extra={"examples": [{
        "tipo": "cliente", "nombre": "Juan Pérez", "tipo_documento": "CC", "numero_documento": "1020304050",
        "telefono": "3001234567", "correo": "juan@cliente.com", "contrasena": "Cliente123*"}]})

    tipo: Literal["cliente"]
    nombre: NombreUsuario = Field(description="**Obligatorio.** De 1 a 100 caracteres.", examples=["Juan Pérez"])
    tipo_documento: Annotated[TipoDocumento, AfterValidator(_no_vacio)] = Field(
        description="**Obligatorio.** `CC`, `NIT`, `CE` o `PA`.", examples=["CC"])
    numero_documento: Documento = Field(
        description="**Obligatorio.** Solo números, hasta 30 (con `PA` también letras). Debe ser único.", examples=["1020304050"])
    telefono: TelefonoObligatorio = Field(description="**Obligatorio.** Solo números, de 7 a 15 dígitos.", examples=["3001234567"])
    correo: Correo = Field(description="**Obligatorio.** Formato de correo, hasta 100 caracteres. Debe ser único.",
                           examples=["juan@cliente.com"])
    contrasena: Contrasena = Field(description="**Obligatorio.** De 8 a 72 caracteres.", examples=["Cliente123*"])

    @field_validator("numero_documento", mode="after")
    @classmethod
    def documento_segun_tipo(cls, valor, info: ValidationInfo):
        """Solo números (o letras y números si es pasaporte). Si el tipo vino mal, ya hay un error por el tipo."""
        mensaje = error_documento(info.data["tipo_documento"], valor) if "tipo_documento" in info.data else None
        if mensaje:
            raise PydanticCustomError("documento", mensaje)
        return valor


class RegistroEmpresa(BaseModel):
    """Registro de una empresa: queda pendiente hasta que un admin la apruebe. También crea su usuario."""
    model_config = ConfigDict(json_schema_extra={"examples": [{
        "tipo": "empresa", "razon_social": "Distribuidora Andina S.A.S.", "nit": "900123456-1", "telefono": "3001234567",
        "direccion": "Calle 10 # 20-30", "representante": "Ana Torres", "correo": "empresa@entrega.com",
        "contrasena": "Empresa123*"}]})

    tipo: Literal["empresa"]
    razon_social: Texto100 = Field(description="**Obligatorio.** De 1 a 100 caracteres.", examples=["Distribuidora Andina S.A.S."])
    nit: Nit = Field(description="**Obligatorio.** Con dígito de verificación. Único sin contar ese dígito.", examples=["900123456-1"])
    telefono: TelefonoObligatorio = Field(description="**Obligatorio.** Solo números, de 7 a 15 dígitos.", examples=["3001234567"])
    direccion: Texto200 = Field(description="**Obligatorio.** De 1 a 200 caracteres.", examples=["Calle 10 # 20-30"])
    representante: Texto100 = Field(description="**Obligatorio.** Representante legal; será el nombre del usuario.",
                                    examples=["Ana Torres"])
    correo: Correo = Field(description="**Obligatorio.** Con este correo entra el usuario de la empresa. Debe ser único.",
                           examples=["empresa@entrega.com"])
    contrasena: Contrasena = Field(description="**Obligatorio.** De 8 a 72 caracteres.", examples=["Empresa123*"])


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
