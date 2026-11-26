# Endpoints de Clientes: buscar el cliente al que se le va a facturar.
# Aquí solo están las rutas y su documentación. La lógica está en services.py, las consultas en queries.py
# y los ejemplos de error de /docs en errors.py.
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.deps import get_current_user, require_permiso
from app.core.docs import ERROR_401, ERROR_403
from app.modulos.clientes import services
from app.modulos.clientes.errors import DOC_422_BUSCAR
from app.modulos.clientes.schemas import MIN_BUSQUEDA, ClientePaginado, TextoBusqueda
from app.modulos.usuarios.models import Usuario

# Busca clientes quien puede facturar (los permisos se leen de la BD en cada petición; el rol admin siempre pasa)
puede_facturar = require_permiso("facturas_create")

router = APIRouter(
    prefix="/clientes",
    tags=["Clientes"],
    dependencies=[Depends(get_current_user)],
)


# ===== CONSULTAS (GET) =====

@router.get(
    "/buscar",
    response_model=ClientePaginado,
    summary="Buscar clientes para facturar",
    description=f"""
Busca entre los clientes **activos** el adquiriente de una factura. Reemplaza a `GET /facturas/clientes`.

**Permiso requerido:** `facturas_create`. El rol `admin` siempre tiene acceso. Requiere `Authorization: Bearer <token>`.

**Parámetros:**
- `q` (**obligatorio**, mínimo {MIN_BUSQUEDA} caracteres sin contar los espacios del inicio y del final): busca en el **nombre**,
  el **número de documento** o el **correo** (contiene, sin distinguir mayúsculas ni tildes).
- `page`: número de página, empieza en 1.
- `limit`: elementos por página, por defecto 10 y máximo 100.

**Alcance:** los clientes **no pertenecen a ninguna empresa**, así que cualquiera que pueda facturar los encuentra a todos.
Nunca salen los demás usuarios (admin, empresa o bodegueros), ni los de la propia empresa.

**Devuelve:** `{{"data": [...], "total": n, "page": p, "limit": l}}`, ordenado por nombre. Cada fila trae solo `id`, `nombre`,
`tipo_documento` y `numero_documento`. El `id` es el que se envía como `cliente_id` en `POST /facturas`.
""",
    response_description="Página de clientes activos que coinciden con la búsqueda",
    responses={
        401: ERROR_401,
        403: ERROR_403,
        422: DOC_422_BUSCAR,
    },
)
def buscar_clientes(
    # Query va DENTRO de Annotated: con "= Query(...)" FastAPI descarta las validaciones de TextoBusqueda
    q: Annotated[TextoBusqueda, Query(description="Texto a buscar en el nombre, el documento o el correo. "
                                                  f"Mínimo {MIN_BUSQUEDA} caracteres.")],
    page: int = Query(1, ge=1, description="Número de página. Empieza en 1."),
    limit: int = Query(10, ge=1, le=100, description="Elementos por página. Por defecto 10, máximo 100."),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(puede_facturar),
):
    """Clientes activos (datos mínimos) que coinciden con la búsqueda."""
    return services.buscar_clientes(q, page, limit, db)
