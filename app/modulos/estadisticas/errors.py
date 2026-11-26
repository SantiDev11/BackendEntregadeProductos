# Errores del módulo Estadísticas: los mensajes, las funciones que los lanzan y los ejemplos que muestra /docs.
from app.core.docs import respuesta_error
from app.core.errors import error_403, error_422

# ===== MENSAJES =====

MSG_RANGO_INVALIDO = "debe ser igual o posterior a fecha_inicio"
MSG_RANGO_ANTERIOR = "debe ser igual o posterior a desde"  # parámetros en desuso
MSG_SIN_PERMISO = "No tiene permiso para esta acción"


# ===== FUNCIONES QUE LANZAN EL ERROR (uso: raise errors.rango_invalido()) =====

def rango_invalido():
    """422 cuando `fecha_fin` es anterior a `fecha_inicio` (mismo formato que los 422 de FastAPI)."""
    return error_422("fecha_fin", MSG_RANGO_INVALIDO, origen="query")


def rango_anterior_invalido():
    """Lo mismo, con los parámetros en desuso (`desde` y `hasta`)."""
    return error_422("hasta", MSG_RANGO_ANTERIOR, origen="query")


def estado_invalido(opciones):
    """422 cuando `estado` no es uno de los que puede usar el rol."""
    opciones = list(opciones)
    return error_422("estado", f"debe ser {', '.join(opciones[:-1])} o {opciones[-1]}", origen="query")


def bodega_de_otra_empresa():
    """403 cuando una empresa filtra por una bodega que no es suya (o que no existe: no se revela cuál de las dos)."""
    return error_403(MSG_SIN_PERMISO)


# ===== EJEMPLOS DE ERROR PARA /docs =====

DOC_422_RESUMEN = respuesta_error(
    "Algún parámetro de la consulta no es válido",
    fecha_invalida="fecha_inicio: tiene un formato inválido",
    rango_invalido=f"fecha_fin: {MSG_RANGO_INVALIDO}",
    estado_invalido="estado: debe ser todas, pendientes, completadas o rechazadas",
    id_invalido="bodega_id: tiene un formato inválido",
)
DOC_403_RESUMEN = respuesta_error("Sin el permiso, o una empresa filtra por una bodega que no es suya", sin_permiso=MSG_SIN_PERMISO)
