# Errores del módulo Facturas: los mensajes, las funciones que los lanzan y los ejemplos que muestra /docs.
from app.core.docs import respuesta_error
from app.core.errors import error_422, error_400, error_403, error_404
from app.modulos.facturas.schemas import MSG_MOTIVO_CORTO, MSG_MOTIVO_FALTA, MSG_MOTIVO_LARGO, MSG_NUMERO

# ===== MENSAJES =====

MSG_NO_ENCONTRADA = "Factura no encontrada"
MSG_SOLO_CLIENTE = "Solo el cliente de la factura puede aceptarla o rechazarla"
MSG_ESTADO_INVALIDO = "La factura no está en un estado válido para esta acción"
MSG_CLIENTE = "El cliente indicado no existe o no es un cliente activo"
MSG_BODEGA = "La bodega indicada no existe, está inactiva o no le pertenece"
MSG_TIPOS = "Uno o más tipos no existen"
MSG_TIPOS_BODEGA = "Uno o más tipos no pertenecen a la bodega de la factura"
MSG_TIPOS_INACTIVOS = "Uno o más tipos están inactivos"


# ===== FUNCIONES QUE LANZAN EL ERROR (uso: raise errors.factura_no_encontrada()) =====

def factura_no_encontrada():
    return error_404(MSG_NO_ENCONTRADA)


def solo_el_cliente():
    return error_403(MSG_SOLO_CLIENTE)


def estado_invalido():
    return error_400(MSG_ESTADO_INVALIDO)


def cliente_invalido():
    return error_400(MSG_CLIENTE)


def bodega_invalida():
    return error_400(MSG_BODEGA)


def tipos_no_existen():
    return error_400(MSG_TIPOS)


def tipos_de_otra_bodega():
    return error_400(MSG_TIPOS_BODEGA)


def tipos_inactivos():
    return error_400(MSG_TIPOS_INACTIVOS)


def estado_filtro_invalido():
    """422 del filtro ?estado= del listado (mismo formato que los 422 de FastAPI)."""
    return error_422("estado", "debe ser emitida, entregada, firmada, rechazada o recibida", origen="query")


def fecha_vencimiento_obligatoria():
    """422 cuando la forma de pago es crédito y no llega fecha_vencimiento."""
    return error_422("fecha_vencimiento", "es obligatoria cuando la forma de pago es crédito")


# ===== EJEMPLOS DE ERROR PARA /docs =====

DOC_404 = respuesta_error("No existe la factura o el usuario no puede verla", no_existe=MSG_NO_ENCONTRADA)
DOC_422_ID = respuesta_error("El id de la ruta no es un número", id_invalido="factura_id: tiene un formato inválido")
DOC_400_ESTADO = respuesta_error("La acción no corresponde al estado actual de la factura", estado_invalido=MSG_ESTADO_INVALIDO)
DOC_403_GESTION = respuesta_error("Solo `admin` y `bodeguero`", sin_permiso="No tiene permiso para esta acción")
DOC_403_CLIENTE = respuesta_error(
    "Sin el permiso, o no es el cliente de la factura",
    sin_permiso="No tiene permiso para esta acción",
    no_es_el_cliente=MSG_SOLO_CLIENTE,
)
DOC_422_LISTAR_FACTURAS = respuesta_error(
    "Algún parámetro de la consulta no es válido",
    estado_invalido="estado: debe ser emitida, entregada, firmada, rechazada o recibida",
    limit_maximo="limit: debe ser menor o igual a 100",
    page_minimo="page: debe ser mayor o igual a 1",
)
DOC_422_LISTAR_CLIENTES_PARA_FACTURAR = respuesta_error(
    "Algún parámetro de la consulta no es válido",
    limit_maximo="limit: debe ser menor o igual a 100",
    page_minimo="page: debe ser mayor o igual a 1",
)
DOC_400_CREAR = respuesta_error("Cliente, bodega o tipos inválidos", cliente=MSG_CLIENTE, bodega=MSG_BODEGA, tipos=MSG_TIPOS,
                             tipos_otra_bodega=MSG_TIPOS_BODEGA, tipos_inactivos=MSG_TIPOS_INACTIVOS)
DOC_422_CREAR = respuesta_error(
    "El cuerpo no cumple las validaciones",
    faltantes="cliente_id: es obligatorio; bodega_id: es obligatorio; forma_pago: es obligatorio; "
              "medio_pago: es obligatorio; detalle: es obligatorio",
    linea_incompleta="tipo_id: es obligatorio; unidad_medida: es obligatorio",
    detalle_vacio="detalle: debe tener al menos 1 elemento(s)",
    cantidad="cantidad: debe ser mayor que 0",
    numero_como_texto=f"cantidad: {MSG_NUMERO}; precio_unitario: {MSG_NUMERO}",
    iva="iva_porcentaje: debe ser 0, 5 o 19",
    credito="fecha_vencimiento: es obligatoria cuando la forma de pago es crédito",
    forma_pago="forma_pago: debe ser contado o credito",
)
DOC_400_ACTUALIZAR = respuesta_error("Estado inválido, o cliente, bodega o tipos inválidos",
    estado_invalido=MSG_ESTADO_INVALIDO, cliente=MSG_CLIENTE, bodega=MSG_BODEGA, tipos=MSG_TIPOS,
tipos_otra_bodega=MSG_TIPOS_BODEGA, tipos_inactivos=MSG_TIPOS_INACTIVOS)
DOC_422_ACTUALIZAR = respuesta_error(
    "El id o el cuerpo no cumplen las validaciones",
    id_invalido="factura_id: tiene un formato inválido",
    credito="fecha_vencimiento: es obligatoria cuando la forma de pago es crédito",
    cantidad="cantidad: debe ser mayor que 0",
    numero_como_texto=f"cantidad: {MSG_NUMERO}; precio_unitario: {MSG_NUMERO}",
)
DOC_422_ACEPTAR = respuesta_error(
    "La firma no es válida",
    faltante="firma: es obligatorio",
    formato="firma: debe ser una imagen PNG en base64 (data:image/png;base64,...)",
    base64="firma: no es un base64 válido",
    grande="firma: es demasiado grande (máximo 500 KB)",
)
DOC_422_RECHAZAR = respuesta_error(
    "El motivo no es válido",
    faltante=f"motivo_rechazo: {MSG_MOTIVO_FALTA}",
    corto=f"motivo_rechazo: {MSG_MOTIVO_CORTO}",
    largo=f"motivo_rechazo: {MSG_MOTIVO_LARGO}",
)
