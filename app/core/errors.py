# Manejo de errores: convierte los 422 de FastAPI en
#   {"detail": "texto legible", "errores": {"campo": "mensaje", "detalle[0].cantidad": "mensaje"}}
# "detail" es un solo texto con todo (compatible con lo que ya usa el frontend);
# "errores" trae un mensaje por campo, con la ruta completa (incluye la posición en las listas).
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

# Partes de "loc" que no son nombres de campo
PREFIJOS_LOC = {"body", "query", "path"}

# Traducción de los tipos de error más comunes de Pydantic
TRADUCCIONES = {
    "missing": "es obligatorio",
    "string_too_short": "es demasiado corto",
    "string_too_long": "es demasiado largo",
}

# Límites numéricos (ge, le, gt, lt): el valor del límite viene en error["ctx"]
LIMITES_NUMERICOS = {
    "greater_than_equal": ("ge", "debe ser mayor o igual a {}"),
    "less_than_equal": ("le", "debe ser menor o igual a {}"),
    "greater_than": ("gt", "debe ser mayor que {}"),
    "less_than": ("lt", "debe ser menor que {}"),
    "too_short": ("min_length", "debe tener al menos {} elemento(s)"),
    "decimal_max_places": ("decimal_places", "debe tener máximo {} decimales"),
    "decimal_max_digits": ("max_digits", "debe tener máximo {} dígitos"),
}


def _nombre_campo(loc) -> str | None:
    """Devuelve el último elemento de loc que sea un nombre de campo.
    Se ignoran las posiciones de listas (0, 1, 2...): en ["permisos_ids", 0] el campo es "permisos_ids"."""
    partes = [str(p) for p in loc if p not in PREFIJOS_LOC and not isinstance(p, int)]
    return partes[-1] if partes else None


def _ruta_campo(loc) -> str:
    """Ruta completa del campo: ("body", "detalle", 0, "cantidad") -> "detalle[0].cantidad".
    Si el error es del cuerpo completo (sin campo), devuelve "general"."""
    ruta = ""
    for parte in loc:
        if parte in PREFIJOS_LOC:
            continue
        if isinstance(parte, int):
            ruta += f"[{parte}]"
        else:
            ruta += f".{parte}" if ruta else str(parte)
    return ruta or "general"


def _mensaje(error: dict) -> str:
    """Traduce un error de Pydantic a un mensaje en español."""
    tipo = error.get("type", "")
    mensaje = error.get("msg", "")

    # Texto vacío en un campo obligatorio (mínimo 1 carácter): "" o solo espacios
    if tipo == "string_too_short" and error.get("ctx", {}).get("min_length") == 1:
        return "no puede estar vacío"
    if tipo in TRADUCCIONES:
        return TRADUCCIONES[tipo]
    # Límites numéricos, por ejemplo page >= 1 o limit <= 100
    if tipo in LIMITES_NUMERICOS:
        clave, plantilla = LIMITES_NUMERICOS[tipo]
        return plantilla.format(error.get("ctx", {}).get(clave, ""))
    # EmailStr reporta el correo mal formado como value_error con "email" en el mensaje
    if tipo == "value_error" and "email" in mensaje.lower():
        return "formato de correo inválido"
    # Número o tipo incorrecto: int_parsing, int_type, string_type, bool_parsing, etc.
    if tipo.endswith("_parsing") or tipo.endswith("_type"):
        return "tiene un formato inválido"
    # Cualquier otro caso: mensaje original de Pydantic
    return mensaje


def respuesta_422(errores: list[dict]) -> JSONResponse:
    """Arma la respuesta 422 a partir de una lista de errores con el formato de Pydantic (type, loc, msg)."""
    # El cuerpo no se pudo leer como JSON
    if any(e.get("type") == "json_invalid" for e in errores):
        mensaje = "El cuerpo de la petición no es un JSON válido"
        return JSONResponse(status_code=422, content={"detail": mensaje, "errores": {"general": mensaje}})

    partes = []
    por_campo: dict[str, str] = {}
    for error in errores:
        loc = error.get("loc", ())
        campo = _nombre_campo(loc)
        mensaje = _mensaje(error)
        partes.append(f"{campo}: {mensaje}" if campo else mensaje)

        ruta = _ruta_campo(loc)
        por_campo[ruta] = f"{por_campo[ruta]}; {mensaje}" if ruta in por_campo else mensaje

    return JSONResponse(status_code=422, content={"detail": "; ".join(partes), "errores": por_campo})


def error_422(campo: str, mensaje: str, origen: str = "body") -> RequestValidationError:
    """Crea un 422 manual (desde un endpoint) con el mismo formato que los de Pydantic.
    Uso: raise error_422("fecha_vencimiento", "es obligatoria cuando la forma de pago es crédito")"""
    return RequestValidationError([{"type": "regla_negocio", "loc": (origen, campo), "msg": mensaje, "input": None}])


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Responde 422 con un texto que resume todos los errores y un mensaje por campo."""
    return respuesta_422(exc.errors())
