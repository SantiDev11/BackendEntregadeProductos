# Errores del módulo Tipos: los mensajes, las funciones que los lanzan y los ejemplos que muestra /docs.
from app.core.docs import respuesta_error
from app.core.errors import error_400, error_403, error_404
from app.modulos.tipos.schemas import MSG_BOOLEANO, MSG_NUMERO

# ===== MENSAJES =====

MSG_NO_ENCONTRADO = "Tipo no encontrado"
MSG_NOMBRE_DUPLICADO = "Ya existe un tipo con ese nombre en esta bodega"
MSG_USADO_EN_FACTURAS = "No se puede eliminar: el tipo está usado en facturas"
MSG_SIN_BODEGA = "No tiene una bodega asignada: no puede crear tipos"
MSG_VARIAS_BODEGAS = "Tiene varias bodegas: indique bodega_id con una de las suyas"
MSG_BODEGA_INVALIDA = "La bodega indicada no existe o no le pertenece"
MSG_TIPO_AJENO = "El tipo no pertenece a su bodega"


# ===== FUNCIONES QUE LANZAN EL ERROR (uso: raise errors.tipo_no_encontrado()) =====

def tipo_no_encontrado():
    return error_404(MSG_NO_ENCONTRADO)


def tipo_ajeno():
    return error_403(MSG_TIPO_AJENO)


def nombre_duplicado():
    return error_400(MSG_NOMBRE_DUPLICADO)


def sin_bodega():
    return error_400(MSG_SIN_BODEGA)


def varias_bodegas():
    return error_400(MSG_VARIAS_BODEGAS)


def bodega_invalida():
    return error_400(MSG_BODEGA_INVALIDA)


def usado_en_facturas():
    return error_400(MSG_USADO_EN_FACTURAS)


# ===== EJEMPLOS DE ERROR PARA /docs =====

DOC_404 = respuesta_error("No existe un tipo con ese id", no_existe=MSG_NO_ENCONTRADO)
DOC_403_TIPO = respuesta_error(
    "Sin el permiso, o el tipo es de una bodega que no es del usuario",
    sin_permiso="No tiene permiso para esta acción",
    tipo_ajeno=MSG_TIPO_AJENO,
)
DOC_422_ID = respuesta_error("El id de la ruta no es un número", id_invalido="tipo_id: tiene un formato inválido")
DOC_403_LISTAR = respuesta_error("Sin el permiso", sin_permiso="No tiene permiso para esta acción")
DOC_422_LISTAR = respuesta_error(
    "Algún parámetro de la consulta no es válido",
    limit_maximo="limit: debe ser menor o igual a 100",
    page_minimo="page: debe ser mayor o igual a 1",
    estado_invalido="estado: tiene un formato inválido",
    bodega_invalida="bodega_id: tiene un formato inválido",
)
DOC_400_CREAR = respuesta_error(
    "Nombre repetido en la bodega, o problema con la bodega",
    duplicado=MSG_NOMBRE_DUPLICADO,
    sin_bodega=MSG_SIN_BODEGA,
    varias_bodegas=MSG_VARIAS_BODEGAS,
    bodega_invalida=MSG_BODEGA_INVALIDA,
)
DOC_422_CREAR = respuesta_error(
    "El cuerpo no cumple las validaciones",
    nombre_faltante="nombre: es obligatorio",
    nombre_vacio="nombre: no puede estar vacío",
    nombre_largo="nombre: es demasiado largo",
    bodega_como_texto=f"bodega_id: {MSG_NUMERO}",
    json_invalido="El cuerpo de la petición no es un JSON válido",
)
DOC_400_ACTUALIZAR = respuesta_error(
    "Nombre repetido en la bodega, o bodega inválida (admin)",
    duplicado=MSG_NOMBRE_DUPLICADO,
    bodega_invalida=MSG_BODEGA_INVALIDA,
)
DOC_422_ACTUALIZAR = respuesta_error(
    "El id o el cuerpo no cumplen las validaciones",
    id_invalido="tipo_id: tiene un formato inválido",
    nombre_vacio="nombre: no puede estar vacío",
    nombre_largo="nombre: es demasiado largo",
    bodega_como_texto=f"bodega_id: {MSG_NUMERO}",
    estado_invalido="estado: tiene un formato inválido",
)
DOC_400_ELIMINAR = respuesta_error("El tipo está usado en facturas", en_uso=MSG_USADO_EN_FACTURAS)
DOC_422_ESTADO = respuesta_error(
    "El id o el cuerpo no cumplen las validaciones",
    id_invalido="tipo_id: tiene un formato inválido",
    estado_faltante="estado: es obligatorio",
    estado_texto=f"estado: {MSG_BOOLEANO}",
)
