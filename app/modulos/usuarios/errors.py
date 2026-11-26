# Errores del módulo Usuarios: los mensajes, las funciones que los lanzan y los ejemplos que muestra /docs.
from app.core.docs import respuesta_error
from app.core.errors import error_400, error_403, error_404, error_422
from app.modulos.empresas.errors import MSG_ID_NO_ACTIVA, MSG_ID_NO_EXISTE, MSG_ID_OBLIGATORIO
from app.modulos.usuarios.schemas import MSG_BOOLEANO, MSG_DOCUMENTO, MSG_NUMERO, MSG_SOLO_NUMEROS, MSG_TELEFONO_LARGO

# ===== MENSAJES =====

MSG_NO_ENCONTRADO = "Usuario no encontrado"
MSG_PERMISO_NO_ENCONTRADO = "Permiso no encontrado"
MSG_DESACTIVARSE = "No puede desactivar su propio usuario"
MSG_PERMISOS_NO_EXISTEN = "Uno o más permisos no existen"
MSG_ELIMINARSE = "No puede eliminar su propio usuario"
MSG_TIENE_FACTURAS = "No se puede eliminar: el usuario tiene facturas asociadas"
MSG_TIENE_BODEGAS = "No se puede eliminar: el usuario tiene bodegas asignadas"
MSG_SIN_PERMISO = "No tiene permiso para esta acción"
MSG_CORREO_DUPLICADO = "Ya existe un usuario con ese correo"
MSG_ROL_NO_EXISTE = "El rol indicado no existe"
MSG_ROL_INACTIVO = "El rol indicado no está activo"
MSG_DOCUMENTO_DUPLICADO = "Ya existe un usuario con ese documento"


# ===== FUNCIONES QUE LANZAN EL ERROR (uso: raise errors.usuario_no_encontrado()) =====

def usuario_no_encontrado():
    return error_404(MSG_NO_ENCONTRADO)


def correo_duplicado():
    return error_400(MSG_CORREO_DUPLICADO)


def rol_no_existe():
    return error_400(MSG_ROL_NO_EXISTE)


def rol_inactivo():
    return error_400(MSG_ROL_INACTIVO)


def permiso_no_encontrado():
    return error_404(MSG_PERMISO_NO_ENCONTRADO)


def documento_duplicado():
    return error_400(MSG_DOCUMENTO_DUPLICADO)


def no_puede_desactivarse():
    return error_400(MSG_DESACTIVARSE)


def permisos_no_existen():
    return error_400(MSG_PERMISOS_NO_EXISTEN)


def no_puede_eliminarse():
    return error_400(MSG_ELIMINARSE)


def tiene_facturas():
    return error_400(MSG_TIENE_FACTURAS)


def tiene_bodegas():
    return error_400(MSG_TIENE_BODEGAS)


def rol_no_permitido():
    """403: una empresa solo puede crear y tener bodegueros."""
    return error_403(MSG_SIN_PERMISO)


def rol_obligatorio():
    """422 cuando falta rol_id (solo lo puede omitir una empresa: se le asigna bodeguero)."""
    return error_422("rol_id", "es obligatorio")


# ===== EJEMPLOS DE ERROR PARA /docs =====

DOC_404 = respuesta_error("No existe un usuario con ese id", no_existe=MSG_NO_ENCONTRADO)
DOC_422_ID = respuesta_error("El id de la ruta no es un número", id_invalido="usuario_id: tiene un formato inválido")
DOC_404_USUARIO_O_PERMISO = respuesta_error(
    "No existe el usuario o el permiso",
    usuario=MSG_NO_ENCONTRADO,
    permiso=MSG_PERMISO_NO_ENCONTRADO,
)
DOC_422_IDS = respuesta_error(
    "Algún id de la ruta no es un número",
    usuario_id="usuario_id: tiene un formato inválido",
    permiso_id="permiso_id: tiene un formato inválido",
)
DOC_422_LISTAR = respuesta_error(
    "Algún parámetro de la consulta no es válido",
    limit_maximo="limit: debe ser menor o igual a 100",
    page_minimo="page: debe ser mayor o igual a 1",
    estado_invalido="estado: tiene un formato inválido",
    rol_id_invalido="rol_id: tiene un formato inválido",
)
DOC_400_CREAR = respuesta_error(
    "El correo o el documento ya están registrados, el rol no existe o la empresa no está activa",
    correo_duplicado=MSG_CORREO_DUPLICADO,
    documento_duplicado=MSG_DOCUMENTO_DUPLICADO,
    rol_inexistente=MSG_ROL_NO_EXISTE,
    rol_inactivo=MSG_ROL_INACTIVO,
    empresa_no_activa=MSG_ID_NO_ACTIVA,
)
DOC_422_CREAR = respuesta_error(
    "El cuerpo no cumple las validaciones",
    campos_faltantes="nombre: es obligatorio; correo: es obligatorio; contrasena: es obligatorio; rol_id: es obligatorio",
    correo_invalido="correo: formato de correo inválido",
    contrasena_corta="contrasena: es demasiado corto",
    contrasena_larga="contrasena: es demasiado largo",
    rol_id_invalido=f"rol_id: {MSG_NUMERO}",
    empresa_id_faltante=f"empresa_id: {MSG_ID_OBLIGATORIO}",
    empresa_id_invalido=f"empresa_id: {MSG_NUMERO}",
    empresa_id_inexistente=f"empresa_id: {MSG_ID_NO_EXISTE}",
    tipo_documento_invalido="tipo_documento: debe ser CC, NIT, CE o PA",
    documento_con_simbolos=f"numero_documento: {MSG_DOCUMENTO}",
    telefono_con_letras=f"telefono: {MSG_SOLO_NUMEROS}",
    telefono_largo=f"telefono: {MSG_TELEFONO_LARGO}",
)
DOC_400_ACTUALIZAR = respuesta_error(
    "Correo o documento repetido, rol inexistente o intento de desactivarse a sí mismo",
    correo_duplicado=MSG_CORREO_DUPLICADO,
    documento_duplicado=MSG_DOCUMENTO_DUPLICADO,
    rol_inexistente=MSG_ROL_NO_EXISTE,
    rol_inactivo=MSG_ROL_INACTIVO,
    desactivarse=MSG_DESACTIVARSE,
    empresa_no_activa=MSG_ID_NO_ACTIVA,
)
DOC_422_ACTUALIZAR = respuesta_error(
    "El id o el cuerpo no cumplen las validaciones",
    id_invalido="usuario_id: tiene un formato inválido",
    correo_invalido="correo: formato de correo inválido",
    contrasena_corta="contrasena: es demasiado corto",
    rol_id_invalido=f"rol_id: {MSG_NUMERO}",
    empresa_id_faltante=f"empresa_id: {MSG_ID_OBLIGATORIO}",
    empresa_id_inexistente=f"empresa_id: {MSG_ID_NO_EXISTE}",
    tipo_documento_invalido="tipo_documento: debe ser CC, NIT, CE o PA",
    documento_con_simbolos=f"numero_documento: {MSG_DOCUMENTO}",
    telefono_con_letras=f"telefono: {MSG_SOLO_NUMEROS}",
    telefono_largo=f"telefono: {MSG_TELEFONO_LARGO}",
    estado_invalido="estado: tiene un formato inválido",
)
DOC_400_ASIGNAR = respuesta_error("Algún id no corresponde a un permiso existente", permiso_inexistente=MSG_PERMISOS_NO_EXISTEN)
DOC_422_ASIGNAR = respuesta_error(
    "El id o el cuerpo no cumplen las validaciones",
    id_invalido="usuario_id: tiene un formato inválido",
    lista_faltante="permisos_ids: es obligatorio",
    no_es_lista="permisos_ids: tiene un formato inválido",
    id_como_texto=f"permisos_ids: {MSG_NUMERO}",
)
DOC_400_ELIMINAR = respuesta_error(
    "Intento de eliminar el propio usuario",
    eliminarse=MSG_ELIMINARSE,
    con_facturas=MSG_TIENE_FACTURAS,
    con_bodegas=MSG_TIENE_BODEGAS,
)
DOC_422_ESTADO = respuesta_error(
    "El id o el cuerpo no cumplen las validaciones",
    id_invalido="usuario_id: tiene un formato inválido",
    estado_faltante="estado: es obligatorio",
    estado_texto=f"estado: {MSG_BOOLEANO}",
)
