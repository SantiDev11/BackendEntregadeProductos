# Errores del módulo Clientes: los ejemplos que muestra /docs (los 422 los lanza el propio parámetro).
from app.core.docs import respuesta_error
from app.modulos.clientes.schemas import MSG_BUSQUEDA_CORTA

# ===== EJEMPLOS DE ERROR PARA /docs =====

DOC_422_BUSCAR = respuesta_error(
    "Algún parámetro de la consulta no es válido",
    q_faltante="q: es obligatorio",
    q_corta=f"q: {MSG_BUSQUEDA_CORTA}",
    limit_maximo="limit: debe ser menor o igual a 100",
    page_minimo="page: debe ser mayor o igual a 1",
)
