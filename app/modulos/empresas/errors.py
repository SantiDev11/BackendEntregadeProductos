# Errores del módulo Empresas: los mensajes, las funciones que los lanzan y los ejemplos que muestra /docs.
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from app.core.docs import respuesta_error
from app.core.errors import error_400, error_403, error_404, error_422
from app.modulos.empresas.schemas import (MSG_ESTADO, MSG_MOTIVO_CORTO, MSG_MOTIVO_FALTA, MSG_NIT, MSG_SOLO_NUMEROS,
                                          MSG_TELEFONO_LARGO)

# ===== MENSAJES =====

MSG_NO_ENCONTRADA = "Empresa no encontrada"
MSG_FILTRO_ESTADO = "debe ser pendiente, activa, rechazada o suspendida"
MSG_NIT_DUPLICADO = "Ya existe una empresa con ese NIT"
MSG_PENDIENTE = "Su empresa está pendiente de aprobación"
MSG_RECHAZADA = "Su empresa fue rechazada"
MSG_SUSPENDIDA = "Su empresa está suspendida"
MSG_ID_OBLIGATORIO = "es obligatorio"
MSG_ID_NO_EXISTE = "la empresa indicada no existe"
MSG_ID_NO_ACTIVA = "La empresa indicada no está activa"
MSG_CAMBIO_AL_ELIMINAR = "La empresa cambió mientras se eliminaba. Intente de nuevo"


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


def cambio_al_eliminar():
    return error_400(MSG_CAMBIO_AL_ELIMINAR)


def tiene_datos(datos: list[str]):
    """400 al eliminar: "... tiene facturas"."""
    lista = " y ".join(filter(None, [", ".join(datos[:-1]), datos[-1]]))
    return error_400(f"No se puede eliminar: la empresa tiene {lista}. Puede suspenderla")


def empresa_id_obligatorio():
    """422 cuando el admin no envía el empresa_id de lo que crea."""
    return error_422("empresa_id", MSG_ID_OBLIGATORIO)


def empresa_id_invalido(error: ValidationError):
    """422 cuando el empresa_id no es un número entero."""
    return RequestValidationError([{**e, "loc": ("body", "empresa_id")} for e in error.errors()])


def empresa_id_no_existe():
    """422 cuando el empresa_id no es de ninguna empresa."""
    return error_422("empresa_id", MSG_ID_NO_EXISTE)


def empresa_id_no_activa():
    """400 cuando el empresa_id es de una empresa pendiente, rechazada o suspendida."""
    return error_400(MSG_ID_NO_ACTIVA)


def empresa_no_activa(estado: str, motivo: str | None):
    """403 según el estado. En la rechazada se agrega el motivo, si lo tiene."""
    if estado == "rechazada":
        return error_403(f"{MSG_RECHAZADA}: {motivo}" if motivo else MSG_RECHAZADA)
    return error_403({"pendiente": MSG_PENDIENTE, "suspendida": MSG_SUSPENDIDA}[estado])


# ===== EJEMPLOS DE ERROR PARA /docs =====

DOC_403 = respuesta_error("No es admin", sin_permiso="No tiene permiso para esta acción")
DOC_404 = respuesta_error("No existe una empresa con ese id", no_existe=MSG_NO_ENCONTRADA)
DOC_400_ESTADO = respuesta_error("El cambio de estado no está permitido", cambio="No se puede pasar de activa a rechazada")
DOC_400_CREAR = respuesta_error("El correo o el NIT ya están registrados", correo="Ya existe un usuario con ese correo",
                                nit=MSG_NIT_DUPLICADO)
DOC_400_ACTUALIZAR = respuesta_error("Otra empresa ya tiene ese NIT", nit=MSG_NIT_DUPLICADO)
DOC_400_ELIMINAR = respuesta_error(
    "La empresa tiene facturas, o uno de sus usuarios está a cargo de una bodega de otra empresa",
    con_facturas="No se puede eliminar: la empresa tiene facturas. Puede suspenderla",
    bodega_ajena="No se puede eliminar: la empresa tiene bodegas de otra empresa a cargo de sus usuarios. Puede suspenderla",
    concurrencia=MSG_CAMBIO_AL_ELIMINAR,
)
DOC_422_ID = respuesta_error("El id de la ruta no es un número", id_invalido="empresa_id: tiene un formato inválido")
_EJEMPLOS_422 = {
    "nit_invalido": f"nit: {MSG_NIT}",
    "vacio": "direccion: no puede estar vacío",
    "largo": "razon_social: es demasiado largo",
    "telefono_con_letras": f"telefono: {MSG_SOLO_NUMEROS}",
    "telefono_largo": f"telefono: {MSG_TELEFONO_LARGO}",
    "correo_invalido": "correo: formato de correo inválido",
}
DOC_422_CREAR = respuesta_error("El cuerpo no cumple las validaciones", faltante="nit: es obligatorio",
                                contrasena_corta="contrasena: es demasiado corto", **_EJEMPLOS_422)
DOC_422_ACTUALIZAR = respuesta_error("El id o el cuerpo no cumplen las validaciones",
                                     id_invalido="empresa_id: tiene un formato inválido", **_EJEMPLOS_422)
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
