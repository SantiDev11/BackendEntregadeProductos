# Errores del módulo Estadísticas: los mensajes, las funciones que los lanzan y los ejemplos que muestra /docs.
from app.core.docs import respuesta_error
from app.core.errors import error_422

# ===== MENSAJES =====

MSG_RANGO_INVALIDO = "debe ser igual o posterior a desde"


# ===== FUNCIONES QUE LANZAN EL ERROR (uso: raise errors.rango_invalido()) =====

def rango_invalido():
    """422 cuando `hasta` es anterior a `desde` (mismo formato que los 422 de FastAPI)."""
    return error_422("hasta", MSG_RANGO_INVALIDO, origen="query")


# ===== EJEMPLOS DE ERROR PARA /docs =====

DOC_422_RESUMEN = respuesta_error(
    "Alguna fecha no es válida",
    fecha_invalida="desde: tiene un formato inválido",
    rango_invalido=f"hasta: {MSG_RANGO_INVALIDO}",
)
