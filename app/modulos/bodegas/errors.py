# Errores del módulo Bodegas: los mensajes, las funciones que los lanzan y los ejemplos que muestra /docs.
from app.core.docs import respuesta_error
from app.core.errors import error_400, error_404

# ===== MENSAJES =====

MSG_NO_ENCONTRADA = "Bodega no encontrada"
MSG_NOMBRE_DUPLICADO = "Ya existe una bodega con ese nombre"
MSG_CODIGO_DUPLICADO = "Ya existe una bodega con ese código"
MSG_BODEGUERO_INVALIDO = "El bodeguero indicado no existe o no tiene rol bodeguero"
MSG_TIENE_FACTURAS = "No se puede eliminar: la bodega tiene facturas"
MSG_TIENE_TIPOS = "No se puede eliminar: la bodega tiene tipos"


# ===== FUNCIONES QUE LANZAN EL ERROR (uso: raise errors.bodega_no_encontrada()) =====

def bodega_no_encontrada():
    return error_404(MSG_NO_ENCONTRADA)


def nombre_duplicado():
    return error_400(MSG_NOMBRE_DUPLICADO)


def codigo_duplicado():
    return error_400(MSG_CODIGO_DUPLICADO)


def bodeguero_invalido():
    return error_400(MSG_BODEGUERO_INVALIDO)


def tiene_facturas():
    return error_400(MSG_TIENE_FACTURAS)


def tiene_tipos():
    return error_400(MSG_TIENE_TIPOS)


# ===== EJEMPLOS DE ERROR PARA /docs =====

DOC_404 = respuesta_error("No existe una bodega con ese id, o no le pertenece al bodeguero",
                          no_existe=MSG_NO_ENCONTRADA)
DOC_400_GUARDAR = respuesta_error(
    "Nombre o código repetido, o bodeguero inválido (admin)",
    duplicado=MSG_NOMBRE_DUPLICADO,
    codigo_duplicado=MSG_CODIGO_DUPLICADO,
    bodeguero_invalido=MSG_BODEGUERO_INVALIDO,
)
DOC_400_ELIMINAR = respuesta_error("La bodega tiene facturas o tipos",
                                   en_uso=MSG_TIENE_FACTURAS,
                                   con_tipos=MSG_TIENE_TIPOS)
DOC_422_ID = respuesta_error("El id de la ruta no es un número", id_invalido="bodega_id: tiene un formato inválido")
DOC_422_LISTAR = respuesta_error(
    "Algún parámetro de la consulta no es válido",
    limit_maximo="limit: debe ser menor o igual a 100",
    page_minimo="page: debe ser mayor o igual a 1",
    estado_invalido="estado: tiene un formato inválido",
)
DOC_422_CREAR = respuesta_error(
    "El cuerpo no cumple las validaciones",
    faltantes="codigo: es obligatorio; direccion: es obligatorio; ciudad: es obligatorio; ...",
    nombre_vacio="nombre: no puede estar vacío",
    nombre_largo="nombre: es demasiado largo",
    codigo_largo="codigo: es demasiado largo",
    correo_invalido="correo: formato de correo inválido",
    json_invalido="El cuerpo de la petición no es un JSON válido",
)
DOC_422_EDITAR = respuesta_error(
    "El id o el cuerpo no cumplen las validaciones",
    id_invalido="bodega_id: tiene un formato inválido",
    nombre_vacio="nombre: no puede estar vacío",
    nombre_largo="nombre: es demasiado largo",
    direccion_larga="direccion: es demasiado largo",
    correo_invalido="correo: formato de correo inválido",
    estado_invalido="estado: tiene un formato inválido",
)
