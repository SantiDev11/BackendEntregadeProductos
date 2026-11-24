# Catálogo fijo de permisos (módulo_acción) y plantillas por rol.
# El frontend busca los permisos por NOMBRE, así que estos nombres no deben cambiar.

# (nombre, descripción)
CATALOGO = [
    # Facturación (9)
    ("facturas_view", "Ver facturas"),
    ("facturas_create", "Crear facturas"),
    ("facturas_edit", "Editar facturas"),
    ("facturas_delete", "Eliminar facturas"),
    ("facturas_entregar", "Marcar factura como entregada"),
    ("facturas_recibir", "Registrar la recepción de la factura firmada"),
    ("facturas_aceptar", "Aceptar y firmar factura (cliente)"),
    ("facturas_rechazar", "Rechazar factura (cliente)"),
    ("facturas_pdf", "Descargar PDF de la factura"),
    # Bodegas (4)
    ("bodegas_view", "Ver bodegas"),
    ("bodegas_create", "Crear bodegas"),
    ("bodegas_edit", "Editar bodegas"),
    ("bodegas_delete", "Eliminar bodegas"),
    # Usuarios (4)
    ("usuarios_view", "Ver usuarios"),
    ("usuarios_create", "Crear usuarios"),
    ("usuarios_edit", "Editar usuarios y asignarles permisos"),
    ("usuarios_delete", "Eliminar usuarios"),
    # Tipos / productos (4)
    ("tipos_view", "Ver tipos"),
    ("tipos_create", "Crear tipos"),
    ("tipos_edit", "Editar tipos"),
    ("tipos_delete", "Eliminar tipos"),
    # Roles (4)
    ("roles_view", "Ver roles"),
    ("roles_create", "Crear roles"),
    ("roles_edit", "Editar roles y su plantilla de permisos"),
    ("roles_delete", "Eliminar roles"),
    # Permisos (4)
    ("permisos_view", "Ver permisos"),
    ("permisos_create", "Crear permisos"),
    ("permisos_edit", "Editar permisos"),
    ("permisos_delete", "Eliminar permisos"),
    # Estadísticas (1)
    ("estadisticas_view", "Ver estadísticas"),
]

NOMBRES = {nombre for nombre, _ in CATALOGO}

# Plantilla de cada rol: se copia a los usuarios NUEVOS de ese rol (después cada usuario se maneja aparte)
_FACTURAS_GESTION = ["facturas_view", "facturas_create", "facturas_edit", "facturas_delete",
                     "facturas_entregar", "facturas_recibir", "facturas_pdf"]
PLANTILLAS = {
    "admin": [n for n, _ in CATALOGO if n not in ("facturas_aceptar", "facturas_rechazar")],  # 28
    "bodeguero": ["tipos_view", "tipos_create", "tipos_edit", "tipos_delete",
                  "bodegas_view", "bodegas_create", "bodegas_edit", "bodegas_delete"] + _FACTURAS_GESTION
                 + ["estadisticas_view"],  # 16
    "empresa": ["tipos_view", "tipos_create", "tipos_edit", "tipos_delete",
                "bodegas_view", "bodegas_create", "bodegas_edit", "bodegas_delete",
                "usuarios_view", "usuarios_create", "usuarios_edit", "usuarios_delete"] + _FACTURAS_GESTION
               + ["estadisticas_view"],  # 20
    "cliente": ["facturas_view", "facturas_aceptar", "facturas_rechazar", "facturas_pdf", "estadisticas_view"],  # 5
}

# Nombres viejos que se renombran al sembrar (para no perder asignaciones ya guardadas)
RENOMBRADOS = {"ususarios": "usuarios_view"}
