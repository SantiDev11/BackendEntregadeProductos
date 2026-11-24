# Errores del registro público: los mensajes y los ejemplos que muestra /docs.
# Los de repetidos se reutilizan de Usuarios y Empresas.
from app.core.docs import respuesta_error
from app.modulos.comun.validadores import MSG_SOLO_NUMEROS, MSG_TELEFONO_LARGO
from app.modulos.empresas.errors import MSG_NIT_DUPLICADO
from app.modulos.registro.schemas import MSG_NIT
from app.modulos.usuarios.errors import MSG_CORREO_DUPLICADO, MSG_DOCUMENTO_DUPLICADO

# ===== MENSAJES =====

MSG_TIPO = "debe ser cliente o empresa"


# ===== EJEMPLOS DE ERROR PARA /docs =====

DOC_400 = respuesta_error("El correo, el documento o el NIT ya están registrados", correo=MSG_CORREO_DUPLICADO,
                          documento=MSG_DOCUMENTO_DUPLICADO, nit=MSG_NIT_DUPLICADO)
DOC_422 = respuesta_error(
    "El cuerpo no cumple las validaciones",
    tipo_faltante="tipo: es obligatorio",
    tipo_invalido=f"tipo: {MSG_TIPO}",
    nit_invalido=f"nit: {MSG_NIT}",
    telefono_con_letras=f"telefono: {MSG_SOLO_NUMEROS}",
    telefono_largo=f"telefono: {MSG_TELEFONO_LARGO}",
    correo_invalido="correo: formato de correo inválido",
    contrasena_corta="contrasena: es demasiado corto",
)
