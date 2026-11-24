# Validadores reutilizables para los schemas: campos que solo aceptan números.
# Pydantic por defecto convierte "10" en 10; con estos tipos, un texto en un campo numérico da 422.
from decimal import Decimal
from typing import Annotated

from pydantic import AfterValidator, BeforeValidator, StringConstraints, WithJsonSchema
from pydantic_core import PydanticCustomError

MSG_NUMERO = "debe ser un número"
MSG_SOLO_NUMEROS = "solo puede tener números"
MSG_LETRAS_Y_NUMEROS = "solo puede tener letras y números"
MSG_TELEFONO_LARGO = "debe tener entre 7 y 15 dígitos"


def exigir_numero(valor):
    """Solo deja pasar números del JSON (10 o 10.5). Rechaza textos ("10"), true/false y listas.
    null sigue su curso normal: lo permite o lo rechaza el propio campo."""
    if valor is not None and (isinstance(valor, bool) or not isinstance(valor, (int, float, Decimal))):
        raise PydanticCustomError("no_es_numero", MSG_NUMERO)
    return valor


def solo_digitos(valor: str) -> bool:
    """True si el texto tiene únicamente dígitos 0-9 (sin letras, espacios, puntos ni signos)."""
    return valor.isascii() and valor.isdigit()


def error_documento(tipo: str | None, numero: str | None) -> str | None:
    """Mensaje de error del número de documento según su tipo, o None si es válido.
    Pasaporte (PA): letras y números. Los demás tipos (o sin tipo): solo números. Vacío es válido."""
    if not numero:
        return None
    if tipo == "PA":
        return None if numero.isascii() and numero.isalnum() else MSG_LETRAS_Y_NUMEROS
    return None if solo_digitos(numero) else MSG_SOLO_NUMEROS


def _validar_telefono(valor: str) -> str:
    """Solo dígitos, de 7 a 15. Se permite "" (sirve para borrar el teléfono)."""
    if valor == "":
        return valor
    if not solo_digitos(valor):
        raise PydanticCustomError("solo_numeros", MSG_SOLO_NUMEROS)
    if not 7 <= len(valor) <= 15:
        raise PydanticCustomError("telefono_largo", MSG_TELEFONO_LARGO)
    return valor


def _validar_solo_digitos(valor: str) -> str:
    if not solo_digitos(valor):
        raise PydanticCustomError("solo_numeros", MSG_SOLO_NUMEROS)
    return valor


# Va después de las demás reglas del número en Annotated, para que se ejecute ANTES que ellas
SoloNumero = BeforeValidator(exigir_numero)


def numero_en_docs(**limites) -> WithJsonSchema:
    """En /docs el campo sale como número y nada más (Decimal por defecto sale como "número o texto")."""
    return WithJsonSchema({"type": "number", **limites})


# Id o cualquier número entero enviado como número en el JSON
Entero = Annotated[int, SoloNumero]

# Teléfono: se guarda como texto (puede empezar en 0), pero solo con dígitos
Telefono = Annotated[str, StringConstraints(strip_whitespace=True), AfterValidator(_validar_telefono),
                     WithJsonSchema({"type": "string", "pattern": "^([0-9]{7,15})?$"})]

# Igual, pero no puede quedar vacío
TelefonoObligatorio = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1),
                                AfterValidator(_validar_telefono),
                                WithJsonSchema({"type": "string", "pattern": "^[0-9]{7,15}$"})]

# Documento sin tipo asociado, obligatorio: solo dígitos, hasta 30
DocumentoObligatorio = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30),
                                 AfterValidator(_validar_solo_digitos),
                                 WithJsonSchema({"type": "string", "pattern": "^[0-9]{1,30}$"})]
