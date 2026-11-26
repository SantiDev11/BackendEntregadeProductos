# Esquemas de Empresa (entrada, salida y listado paginado)
import re
from datetime import datetime
from typing import Annotated, List, Optional

from pydantic import (AfterValidator, BaseModel, BeforeValidator, ConfigDict, EmailStr, Field, StringConstraints, ValidationInfo,
                      WithJsonSchema, field_validator)
from pydantic_core import PydanticCustomError

from app.modulos.usuarios.schemas import Contrasena

ESTADOS_DESTINO = ("activa", "rechazada", "suspendida")  # a "pendiente" no se puede volver
MSG_ESTADO = "debe ser activa, rechazada o suspendida"
MSG_MOTIVO_FALTA = "es obligatorio"
MSG_MOTIVO_CORTO = "debe tener al menos 10 caracteres"
MSG_MOTIVO_LARGO = "es demasiado largo"


MSG_SOLO_NUMEROS = "solo puede tener números"
MSG_TELEFONO_LARGO = "debe tener entre 7 y 15 dígitos"
MSG_NIT = "debe tener el formato 900123456-1"
MSG_NUMERO = "debe ser un número"


def _exigir_numero(valor):
    """Solo deja pasar números del JSON (10). Rechaza textos ("10"), true/false y listas.
    null sigue su curso normal: lo permite o lo rechaza el propio campo."""
    if valor is not None and (isinstance(valor, bool) or not isinstance(valor, (int, float))):
        raise PydanticCustomError("no_es_numero", MSG_NUMERO)
    return valor


# Id enviado como número en el JSON: 3, no "3"
Entero = Annotated[int, BeforeValidator(_exigir_numero)]


def _validar_telefono(valor: str) -> str:
    """Solo dígitos (0-9), de 7 a 15."""
    if not (valor.isascii() and valor.isdigit()):
        raise PydanticCustomError("solo_numeros", MSG_SOLO_NUMEROS)
    if not 7 <= len(valor) <= 15:
        raise PydanticCustomError("telefono_largo", MSG_TELEFONO_LARGO)
    return valor


def _correo_hasta_100(valor: str) -> str:
    if len(valor) > 100:
        raise PydanticCustomError("string_too_long", "es demasiado largo")  # lo que cabe en la base
    return valor.lower()  # el correo siempre se guarda en minúsculas


def _validar_nit(valor: str) -> str:
    """900123456-1: de 5 a 15 dígitos, guion y dígito de verificación."""
    if not re.fullmatch(r"[0-9]{5,15}-[0-9]", valor):
        raise PydanticCustomError("nit", MSG_NIT)
    return valor


# Textos obligatorios: se quitan los espacios al inicio y al final y no pueden quedar vacíos
Texto100 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Texto200 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Correo = Annotated[EmailStr, AfterValidator(_correo_hasta_100)]
Nit = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1), AfterValidator(_validar_nit)]

# Teléfono: se guarda como texto (puede empezar en 0), pero solo con dígitos. No puede quedar vacío
TelefonoObligatorio = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1), AfterValidator(_validar_telefono),
                                WithJsonSchema({"type": "string", "pattern": "^[0-9]{7,15}$"})]


def _normalizar(valor):
    """"Activa " -> "activa" antes de validar."""
    return valor.strip().lower() if isinstance(valor, str) else valor


def _validar_estado(valor: str) -> str:
    if valor not in ESTADOS_DESTINO:
        raise PydanticCustomError("estado", MSG_ESTADO)
    return valor


EstadoDestino = Annotated[str, BeforeValidator(_normalizar), AfterValidator(_validar_estado)]


class EmpresaResumen(BaseModel):
    """Empresa de un usuario, como va en /login y /me."""
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(examples=[1])
    razon_social: str = Field(examples=["Distribuidora Andina S.A.S."])
    estado: str = Field(description="`pendiente`, `activa`, `rechazada` o `suspendida`.", examples=["activa"])


class EmpresaCreate(BaseModel):
    """Datos para crear una empresa y su usuario. **Todos obligatorios.** El estado, el rol y los permisos los pone el servidor."""
    model_config = ConfigDict(json_schema_extra={"examples": [{
        "razon_social": "Distribuidora Andina S.A.S.", "nit": "900123456-1", "telefono": "3001234567",
        "direccion": "Calle 10 # 20-30", "representante": "Ana Torres", "correo": "empresa@entrega.com",
        "contrasena": "Empresa123*"}]})

    razon_social: Texto100 = Field(description="**Obligatorio.** De 1 a 100 caracteres.", examples=["Distribuidora Andina S.A.S."])
    nit: Nit = Field(description="**Obligatorio.** Con dígito de verificación. Único sin contar ese dígito.", examples=["900123456-1"])
    telefono: TelefonoObligatorio = Field(description="**Obligatorio.** Solo números, de 7 a 15 dígitos.", examples=["3001234567"])
    direccion: Texto200 = Field(description="**Obligatorio.** De 1 a 200 caracteres.", examples=["Calle 10 # 20-30"])
    representante: Texto100 = Field(description="**Obligatorio.** Representante legal; será el nombre del usuario.",
                                    examples=["Ana Torres"])
    correo: Correo = Field(description="**Obligatorio.** Con este correo entra el usuario de la empresa. Debe ser único.",
                           examples=["empresa@entrega.com"])
    contrasena: Contrasena = Field(description="**Obligatorio.** De 8 a 72 caracteres.", examples=["Empresa123*"])


NO_VACIO = "Si no se envía o llega en `null`, no se cambia. **No puede quedar vacío.**"


class EmpresaUpdate(BaseModel):
    """Datos para editar una empresa: se envían solo los que cambian, pero ninguno puede quedar vacío.
    El estado no se edita aquí (PATCH /empresas/{id}/estado)."""
    model_config = ConfigDict(json_schema_extra={"examples": [{"telefono": "3109876543", "direccion": "Carrera 7 # 10-20"}]})

    razon_social: Optional[Texto100] = Field(default=None, description="De 1 a 100 caracteres. " + NO_VACIO, examples=["Andina S.A.S."])
    nit: Optional[Nit] = Field(default=None, description="Con dígito de verificación; no puede tenerlo **otra** empresa. " + NO_VACIO,
                               examples=["900123456-1"])
    telefono: Optional[TelefonoObligatorio] = Field(default=None, description="Solo números, de 7 a 15 dígitos. " + NO_VACIO,
                                                    examples=["3109876543"])
    direccion: Optional[Texto200] = Field(default=None, description="De 1 a 200 caracteres. " + NO_VACIO, examples=["Carrera 7 # 10-20"])
    representante: Optional[Texto100] = Field(default=None, description="Representante legal. " + NO_VACIO, examples=["Ana Torres"])
    correo: Optional[Correo] = Field(
        default=None, description="Correo de contacto. **No** cambia el correo con el que entra su usuario. " + NO_VACIO,
        examples=["contacto@andina.com"])


class EmpresaEstadoUpdate(BaseModel):
    """Nuevo estado de la empresa."""
    model_config = ConfigDict(json_schema_extra={"examples": [
        {"estado": "activa"}, {"estado": "rechazada", "motivo_rechazo": "El NIT no coincide con el RUT"}]})

    estado: EstadoDestino = Field(description="**Obligatorio.** `activa`, `rechazada` o `suspendida`.", examples=["rechazada"])
    motivo_rechazo: Optional[Annotated[str, StringConstraints(strip_whitespace=True)]] = Field(
        default=None, validate_default=True,
        description="**Obligatorio solo al rechazar**, de 10 a 255 caracteres. Con otro estado se ignora.",
        examples=["El NIT no coincide con el RUT"])

    @field_validator("motivo_rechazo", mode="after")
    @classmethod
    def motivo_segun_estado(cls, valor, info: ValidationInfo):
        if info.data.get("estado") != "rechazada":
            return None
        if valor is None:
            raise PydanticCustomError("motivo", MSG_MOTIVO_FALTA)
        if len(valor) < 10:
            raise PydanticCustomError("motivo", MSG_MOTIVO_CORTO)
        if len(valor) > 255:
            raise PydanticCustomError("motivo", MSG_MOTIVO_LARGO)
        return valor


class EmpresaOut(BaseModel):
    """Empresa como la ve el admin."""
    id: int = Field(examples=[1])
    razon_social: str = Field(examples=["Distribuidora Andina S.A.S."])
    nit: Optional[str] = Field(default=None, description="Con su dígito de verificación.", examples=["900123456-1"])
    correo: Optional[str] = Field(default=None, examples=["empresa@entrega.com"])
    telefono: Optional[str] = Field(default=None, examples=["3001234567"])
    direccion: Optional[str] = Field(default=None, examples=["Calle 10 # 20-30"])
    representante: Optional[str] = Field(default=None, examples=["Ana Torres"])
    estado: str = Field(description="`pendiente`, `activa`, `rechazada` o `suspendida`.", examples=["pendiente"])
    motivo_rechazo: Optional[str] = Field(default=None, description="Solo si está rechazada.")
    fecha_registro: datetime = Field(examples=["2026-11-24T10:30:00"])
    total_bodegueros: int = Field(examples=[0])
    total_bodegas: int = Field(examples=[0])
    total_facturas: int = Field(examples=[0])


class EmpresaPaginado(BaseModel):
    """Respuesta del listado: {data, total, page, limit}."""
    data: List[EmpresaOut] = Field(description="Empresas de la página, de la más reciente a la más antigua.")
    total: int = Field(description="Cantidad total de empresas que cumplen los filtros (no solo las de esta página).", examples=[3])
    page: int = Field(description="Página devuelta (empieza en 1).", examples=[1])
    limit: int = Field(description="Cantidad máxima de elementos por página.", examples=[10])
