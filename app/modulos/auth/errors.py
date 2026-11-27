# Errores del módulo Auth: los mensajes, las funciones que los lanzan y los ejemplos que muestra /docs.
from app.core.docs import respuesta_error
from app.core.errors import error_401, error_422
from app.modulos.empresas.errors import MSG_PENDIENTE, MSG_RECHAZADA, MSG_SUSPENDIDA

# ===== MENSAJES =====

MSG_CREDENCIALES = "Correo o contraseña incorrectos"
MSG_REFRESH_INVALIDO = "Refresh token inválido o vencido"


# ===== FUNCIONES QUE LANZAN EL ERROR (uso: raise errors.credenciales_invalidas()) =====

def credenciales_invalidas():
    return error_401(MSG_CREDENCIALES)


def identificador_obligatorio():
    """422: no llegó ni `correo` ni `identificador`. Se reporta en `correo`, como antes."""
    return error_422("correo", "es obligatorio")


def refresh_invalido():
    return error_401(MSG_REFRESH_INVALIDO)


# ===== EJEMPLOS DE ERROR PARA /docs =====

DOC_401_LOGIN = respuesta_error(
    "El correo no existe o la contraseña es incorrecta",
    credenciales_invalidas=MSG_CREDENCIALES,
)
DOC_401_REFRESH = respuesta_error(
    "El refresh token no es válido, está vencido o el usuario fue desactivado",
    refresh_invalido=MSG_REFRESH_INVALIDO,
)
DOC_403_EMPRESA = respuesta_error(
    "La empresa del usuario no está activa",
    pendiente=MSG_PENDIENTE,
    rechazada=f"{MSG_RECHAZADA}: <motivo>",
    suspendida=MSG_SUSPENDIDA,
)
DOC_422_LOGIN = respuesta_error(
    "El cuerpo no cumple las validaciones",
    sin_contrasena="contrasena: es obligatorio",
    sin_correo_ni_identificador="correo: es obligatorio",
    correo_vacio="correo: no puede estar vacío",
    json_invalido="El cuerpo de la petición no es un JSON válido",
)
DOC_422_REFRESH = respuesta_error(
    "El cuerpo no cumple las validaciones",
    campos_faltantes="refresh_token: es obligatorio",
    json_invalido="El cuerpo de la petición no es un JSON válido",
)
