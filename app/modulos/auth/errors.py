# Errores del módulo Auth: los mensajes, las funciones que los lanzan y los ejemplos que muestra /docs.
from app.core.docs import respuesta_error
from app.core.errors import error_401

# ===== MENSAJES =====

MSG_CREDENCIALES = "Correo o contraseña incorrectos"


# ===== FUNCIONES QUE LANZAN EL ERROR (uso: raise errors.credenciales_invalidas()) =====

def credenciales_invalidas():
    return error_401(MSG_CREDENCIALES)


# ===== EJEMPLOS DE ERROR PARA /docs =====

DOC_401_LOGIN = respuesta_error(
    "El correo no existe o la contraseña es incorrecta",
    credenciales_invalidas=MSG_CREDENCIALES,
)
DOC_422_LOGIN = respuesta_error(
    "El cuerpo no cumple las validaciones",
    campos_faltantes="correo: es obligatorio; contrasena: es obligatorio",
    correo_invalido="correo: formato de correo inválido",
    json_invalido="El cuerpo de la petición no es un JSON válido",
)
