# Errores del módulo Permisos: los mensajes, las funciones que los lanzan y los ejemplos que muestra /docs.
from app.core.docs import respuesta_error
from app.core.errors import error_400, error_404

# ===== MENSAJES =====

MSG_NO_ENCONTRADO = "Permiso no encontrado"
MSG_NOMBRE_DUPLICADO = "Ya existe un permiso con ese nombre"
MSG_ASIGNADO_A_ROLES = "No se puede eliminar: el permiso está asignado a uno o más roles"
MSG_ASIGNADO_A_USUARIOS = "No se puede eliminar: el permiso está asignado a uno o más usuarios"


# ===== FUNCIONES QUE LANZAN EL ERROR (uso: raise errors.permiso_no_encontrado()) =====

def permiso_no_encontrado():
    return error_404(MSG_NO_ENCONTRADO)


def nombre_duplicado():
    return error_400(MSG_NOMBRE_DUPLICADO)


def asignado_a_roles():
    return error_400(MSG_ASIGNADO_A_ROLES)


def asignado_a_usuarios():
    return error_400(MSG_ASIGNADO_A_USUARIOS)


# ===== EJEMPLOS DE ERROR PARA /docs =====

DOC_404 = respuesta_error("No existe un permiso con ese id", no_existe=MSG_NO_ENCONTRADO)
DOC_400_DUPLICADO = respuesta_error(
    "Ya hay otro permiso con ese nombre (sin distinguir mayúsculas)",
    duplicado=MSG_NOMBRE_DUPLICADO,
)
DOC_422_ID = respuesta_error("El id de la ruta no es un número", id_invalido="permiso_id: tiene un formato inválido")
DOC_422_LISTAR = respuesta_error(
    "Algún parámetro de la consulta no es válido",
    limit_maximo="limit: debe ser menor o igual a 100",
    page_minimo="page: debe ser mayor o igual a 1",
    estado_invalido="estado: tiene un formato inválido",
)
DOC_422_CREAR = respuesta_error(
    "El cuerpo no cumple las validaciones",
    nombre_faltante="nombre: es obligatorio",
    nombre_vacio="nombre: no puede estar vacío",
    nombre_largo="nombre: es demasiado largo",
    descripcion_larga="descripcion: es demasiado largo",
    json_invalido="El cuerpo de la petición no es un JSON válido",
)
DOC_422_ACTUALIZAR = respuesta_error(
    "El id o el cuerpo no cumplen las validaciones",
    id_invalido="permiso_id: tiene un formato inválido",
    nombre_vacio="nombre: no puede estar vacío",
    nombre_largo="nombre: es demasiado largo",
    descripcion_larga="descripcion: es demasiado largo",
    estado_invalido="estado: tiene un formato inválido",
)
DOC_400_ELIMINAR = respuesta_error(
    "El permiso está asignado a roles o a usuarios",
    en_roles=MSG_ASIGNADO_A_ROLES,
    en_usuarios=MSG_ASIGNADO_A_USUARIOS,
)
