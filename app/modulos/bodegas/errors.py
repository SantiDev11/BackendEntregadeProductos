# Errores del módulo Bodegas: los mensajes, las funciones que los lanzan y los ejemplos que muestra /docs.
from app.core.docs import respuesta_error
from app.core.errors import error_400, error_404
from app.modulos.bodegas.schemas import MSG_BOOLEANO, MSG_DOCUMENTO, MSG_NUMERO, MSG_SOLO_NUMEROS, MSG_TELEFONO_LARGO
from app.modulos.empresas.errors import MSG_ID_NO_ACTIVA, MSG_ID_NO_EXISTE, MSG_ID_OBLIGATORIO

# ===== MENSAJES =====

MSG_NO_ENCONTRADA = "Bodega no encontrada"
MSG_NOMBRE_DUPLICADO = "Ya existe una bodega con ese nombre"
MSG_CODIGO_DUPLICADO = "Ya existe una bodega con ese código"
MSG_BODEGUERO_INVALIDO = "El bodeguero indicado no existe o no tiene rol bodeguero"
MSG_BODEGUERO_OTRA_EMPRESA = "El bodeguero no pertenece a la empresa de la bodega"
MSG_TIENE_FACTURAS = "No se puede eliminar: la bodega tiene facturas. Puede desactivarla"

MSG_EMPRESA_NO_ACTIVA = "No se puede activar porque la empresa está {}. Reactive primero la empresa"

# ===== FUNCIONES QUE LANZAN EL ERROR (uso: raise errors.bodega_no_encontrada()) =====

def bodega_no_encontrada():
    return error_404(MSG_NO_ENCONTRADA)


def nombre_duplicado():
    return error_400(MSG_NOMBRE_DUPLICADO)


def codigo_duplicado():
    return error_400(MSG_CODIGO_DUPLICADO)


def bodeguero_invalido():
    return error_400(MSG_BODEGUERO_INVALIDO)


def bodeguero_de_otra_empresa():
    return error_400(MSG_BODEGUERO_OTRA_EMPRESA)


def tiene_facturas():
    return error_400(MSG_TIENE_FACTURAS)


def empresa_no_activa(estado: str):
    """400 al activar algo de una empresa pendiente, rechazada o suspendida."""
    return error_400(MSG_EMPRESA_NO_ACTIVA.format(estado))


# ===== EJEMPLOS DE ERROR PARA /docs =====

DOC_404 = respuesta_error("No existe una bodega con ese id, o no le pertenece al bodeguero",
                          no_existe=MSG_NO_ENCONTRADA)
_EJEMPLOS_400 = {
    "duplicado": MSG_NOMBRE_DUPLICADO,
    "codigo_duplicado": MSG_CODIGO_DUPLICADO,
    "bodeguero_invalido": MSG_BODEGUERO_INVALIDO,
    "bodeguero_otra_empresa": MSG_BODEGUERO_OTRA_EMPRESA,
}
DOC_400_CREAR = respuesta_error("Nombre o código repetido, bodeguero inválido o empresa no activa (admin)",
                                **_EJEMPLOS_400, empresa_no_activa=MSG_ID_NO_ACTIVA)
DOC_400_ACTUALIZAR = respuesta_error("Nombre o código repetido, o bodeguero inválido (admin)", **_EJEMPLOS_400)
DOC_400_ELIMINAR = respuesta_error("La bodega tiene facturas", en_uso=MSG_TIENE_FACTURAS)
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
    telefono_con_letras=f"telefono: {MSG_SOLO_NUMEROS}",
    telefono_largo=f"recibe_telefono: {MSG_TELEFONO_LARGO}",
    documento_con_simbolos=f"recibe_documento: {MSG_DOCUMENTO}",
    bodeguero_como_texto=f"bodeguero_id: {MSG_NUMERO}",
    empresa_id_faltante=f"empresa_id: {MSG_ID_OBLIGATORIO}",
    empresa_id_invalido=f"empresa_id: {MSG_NUMERO}",
    empresa_id_inexistente=f"empresa_id: {MSG_ID_NO_EXISTE}",
    json_invalido="El cuerpo de la petición no es un JSON válido",
)
DOC_422_EDITAR = respuesta_error(
    "El id o el cuerpo no cumplen las validaciones",
    id_invalido="bodega_id: tiene un formato inválido",
    nombre_vacio="nombre: no puede estar vacío",
    nombre_largo="nombre: es demasiado largo",
    direccion_larga="direccion: es demasiado largo",
    correo_invalido="correo: formato de correo inválido",
    telefono_con_letras=f"telefono: {MSG_SOLO_NUMEROS}",
    telefono_largo=f"recibe_telefono: {MSG_TELEFONO_LARGO}",
    documento_con_simbolos=f"recibe_documento: {MSG_DOCUMENTO}",
    bodeguero_como_texto=f"bodeguero_id: {MSG_NUMERO}",
    estado_invalido="estado: tiene un formato inválido",
)
DOC_422_ESTADO = respuesta_error(
    "El id o el cuerpo no cumplen las validaciones",
    id_invalido="bodega_id: tiene un formato inválido",
    estado_faltante="estado: es obligatorio",
    estado_texto=f"estado: {MSG_BOOLEANO}",
)
