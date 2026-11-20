# Endpoints de Estadísticas: un solo panel que cambia según quién lo pide.
# Aquí solo están las rutas y su documentación. La lógica está en services.py, las validaciones
# en helpers.py, las consultas en queries.py y los errores (mensajes y ejemplos /docs) en errors.py.
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.deps import get_current_user, require_permiso
from app.core.docs import ERROR_401, ERROR_403
from app.modulos.estadisticas import services
from app.modulos.estadisticas.errors import DOC_422_RESUMEN
from app.modulos.estadisticas.schemas import ResumenOut
from app.modulos.usuarios.models import Usuario

# Permiso que exige el panel (se lee de la BD en cada petición; el rol admin siempre pasa)
puede_ver = require_permiso("estadisticas_view")

router = APIRouter(
    prefix="/estadisticas",
    tags=["Estadísticas"],
    dependencies=[Depends(get_current_user)],
)


@router.get(
    "/resumen",
    response_model=ResumenOut,
    summary="Panel de estadísticas",
    description="""
Devuelve el panel de estadísticas del usuario de la sesión: **tarjetas** (números) y **series** (gráficos).

**Permiso requerido:** `estadisticas_view`. El rol `admin` siempre tiene acceso. Requiere `Authorization: Bearer <token>`.

**Parámetros (opcionales, formato `AAAA-MM-DD`):**
- `desde` y `hasta`: periodo por **fecha de emisión**, ambos días incluidos.
- Sin ninguno: el **mes actual**. Solo `desde`: hasta el fin de ese mes. Solo `hasta`: desde el inicio de ese mes.
- Si `hasta` es anterior a `desde`: 422.

**Qué facturas cuenta (la misma regla de `GET /facturas`, sale del token):**
- `admin`: todas.
- `cliente`: las que creó + las que tienen su `cliente_id` (de estas, nunca las `emitida`).
- Cualquier otro usuario (bodeguero): solo las que creó.

**Qué devuelve cada uno** (lo que un rol no puede ver no se manda):
- **Admin:** tarjetas `facturas`, `facturado`, `pendientes`, `rechazadas`, `usuarios_activos`, `bodegas_activas`;
  series `por_estado`, `por_fecha`, `por_bodega`, `top_productos`.
- **Bodeguero:** tarjetas `facturas`, `facturado`, `pendientes`, `rechazadas`, `bodegas` (las suyas),
  `tipos` (de sus bodegas); series `por_estado`, `por_fecha`, `por_bodega`, `top_productos` (de sus facturas).
- **Cliente:** tarjetas `facturas`, `facturado`, `pendientes` (por firmar), `rechazadas`; series `por_estado`, `por_fecha`.

**Reglas de los números:**
- `facturado` y `top_productos` **no** cuentan las facturas rechazadas.
- `pendientes` = facturas en `entregada` (esperando la firma del cliente).
- `por_fecha` va día por día si el periodo es de hasta 62 días; si es más largo, mes por mes (`AAAA-MM`).
- `usuarios_activos`, `bodegas_activas`, `bodegas` y `tipos` son el total actual (no dependen del periodo).
""",
    response_description="Periodo, rol, tarjetas y series del panel",
    responses={401: ERROR_401, 403: ERROR_403, 422: DOC_422_RESUMEN},
)
def resumen(
    desde: date | None = Query(None, description="Primer día del periodo (AAAA-MM-DD). Por defecto, el inicio del mes."),
    hasta: date | None = Query(None, description="Último día del periodo (AAAA-MM-DD). Por defecto, el fin del mes."),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(puede_ver),
):
    """Panel de estadísticas según el rol del usuario."""
    return services.resumen(db, usuario, desde, hasta)
