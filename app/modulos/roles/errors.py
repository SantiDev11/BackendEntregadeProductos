# Errores del módulo Roles: los mensajes, las funciones que los lanzan y los ejemplos que muestra /docs.
from app.core.docs import respuesta_error
from app.core.errors import error_400, error_403, error_404
from app.modulos.roles.schemas import MSG_BOOLEANO, MSG_NUMERO

# ===== MENSAJES =====

MSG_NO_ENCONTRADO = "Rol no encontrado"
MSG_NOMBRE_DUPLICADO = "Ya existe un rol con ese nombre"
MSG_PERMISOS_NO_EXISTEN = "Uno o más permisos no existen"
MSG_TIENE_USUARIOS = "No se puede eliminar: hay usuarios con este rol. Desactívelo o asigne otro rol a sus usuarios"
MSG_ADMIN_NO_SE_DESACTIVA = "El rol admin no se puede desactivar"
MSG_PROPIO_ROL = "No puede desactivar su propio rol"


# ===== FUNCIONES QUE LANZAN EL ERROR (uso: raise errors.rol_no_encontrado()) =====

def rol_no_encontrado():
    return error_404(MSG_NO_ENCONTRADO)


def nombre_duplicado():
    return error_400(MSG_NOMBRE_DUPLICADO)


def permisos_no_existen():
    return error_400(MSG_PERMISOS_NO_EXISTEN)


def rol_base():
    """403: solo el admin puede cambiarle el nombre a un rol base."""
    return error_403("No tiene permiso para esta acción")


def tiene_usuarios():
    return error_400(MSG_TIENE_USUARIOS)


def admin_no_se_desactiva():
    """400: el sistema siempre necesita poder asignar el rol admin."""
    return error_400(MSG_ADMIN_NO_SE_DESACTIVA)


def propio_rol():
    """400: desactivar su propio rol lo dejaría a él mismo sin acceso."""
    return error_400(MSG_PROPIO_ROL)


# ===== EJEMPLOS DE ERROR PARA /docs =====

DOC_404 = respuesta_error("No existe un rol con ese id", no_existe=MSG_NO_ENCONTRADO)
DOC_400_DUPLICADO = respuesta_error(
    "Ya hay otro rol con ese nombre (sin distinguir mayúsculas)",
    duplicado=MSG_NOMBRE_DUPLICADO,
)
DOC_422_ID = respuesta_error("El id de la ruta no es un número", id_invalido="rol_id: tiene un formato inválido")
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
    id_invalido="rol_id: tiene un formato inválido",
    nombre_vacio="nombre: no puede estar vacío",
    nombre_largo="nombre: es demasiado largo",
    descripcion_larga="descripcion: es demasiado largo",
    estado_invalido="estado: tiene un formato inválido",
)
DOC_400_ESTADO = respuesta_error("Se intentó desactivar el rol admin o el propio rol", rol_admin=MSG_ADMIN_NO_SE_DESACTIVA,
                                 propio_rol=MSG_PROPIO_ROL)
DOC_422_ESTADO = respuesta_error(
    "El id o el cuerpo no cumplen las validaciones",
    id_invalido="rol_id: tiene un formato inválido",
    estado_faltante="estado: es obligatorio",
    estado_texto=f"estado: {MSG_BOOLEANO}",
)
DOC_400_ASIGNAR = respuesta_error(
    "Algún id de la lista no corresponde a un permiso existente",
    permiso_inexistente=MSG_PERMISOS_NO_EXISTEN,
)
DOC_422_ASIGNAR = respuesta_error(
    "El id o el cuerpo no cumplen las validaciones",
    id_invalido="rol_id: tiene un formato inválido",
    lista_faltante="permisos_ids: es obligatorio",
    no_es_lista="permisos_ids: tiene un formato inválido",
    id_como_texto=f"permisos_ids: {MSG_NUMERO}",
)
DOC_400_ELIMINAR = respuesta_error(
    "Hay usuarios que tienen este rol",
    con_usuarios=MSG_TIENE_USUARIOS,
)
