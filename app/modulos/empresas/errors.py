# Errores del módulo Empresas: los mensajes, las funciones que los lanzan y los ejemplos que muestra /docs.
from app.core.docs import respuesta_error
from app.core.errors import error_400, error_403, error_404, error_422
from app.modulos.empresas.schemas import MSG_ESTADO, MSG_MOTIVO_CORTO, MSG_MOTIVO_FALTA

# ===== MENSAJES =====

MSG_NO_ENCONTRADA = "Empresa no encontrada"
MSG_FILTRO_ESTADO = "debe ser pendiente, activa, rechazada o suspendida"
MSG_NIT_DUPLICADO = "Ya existe una empresa con ese NIT"
MSG_PENDIENTE = "Su empresa está pendiente de aprobación"
MSG_RECHAZADA = "Su empresa fue rechazada"
MSG_SUSPENDIDA = "Su empresa está suspendida"


# ===== FUNCIONES QUE LANZAN EL ERROR (uso: raise errors.nit_duplicado()) =====

def empresa_no_encontrada():
    return error_404(MSG_NO_ENCONTRADA)


def cambio_no_permitido(actual: str, nuevo: str):
    return error_400(f"No se puede pasar de {actual} a {nuevo}")


def filtro_estado_invalido():
    """422 del filtro ?estado= del listado (mismo formato que los 422 de FastAPI)."""
    return error_422("estado", MSG_FILTRO_ESTADO, origen="query")


def nit_duplicado():
    return error_400(MSG_NIT_DUPLICADO)


def empresa_no_activa(estado: str, motivo: str | None):
    """403 según el estado. En la rechazada se agrega el motivo, si lo tiene."""
    if estado == "rechazada":
        return error_403(f"{MSG_RECHAZADA}: {motivo}" if motivo else MSG_RECHAZADA)
    return error_403({"pendiente": MSG_PENDIENTE, "suspendida": MSG_SUSPENDIDA}[estado])


# ===== EJEMPLOS DE ERROR PARA /docs =====

DOC_403 = respuesta_error("No es admin", sin_permiso="No tiene permiso para esta acción")
DOC_404 = respuesta_error("No existe una empresa con ese id", no_existe=MSG_NO_ENCONTRADA)
DOC_400_ESTADO = respuesta_error("El cambio de estado no está permitido", cambio="No se puede pasar de activa a rechazada")
DOC_422_LISTAR = respuesta_error(
    "Algún parámetro de la consulta no es válido",
    estado_invalido=f"estado: {MSG_FILTRO_ESTADO}",
    limit_maximo="limit: debe ser menor o igual a 100",
    page_minimo="page: debe ser mayor o igual a 1",
)
DOC_422_ESTADO = respuesta_error(
    "El id o el cuerpo no cumplen las validaciones",
    id_invalido="empresa_id: tiene un formato inválido",
    estado_faltante="estado: es obligatorio",
    estado_invalido=f"estado: {MSG_ESTADO}",
    motivo_faltante=f"motivo_rechazo: {MSG_MOTIVO_FALTA}",
    motivo_corto=f"motivo_rechazo: {MSG_MOTIVO_CORTO}",
)
