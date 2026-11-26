# Endpoints de Estadísticas: un solo panel que cambia según quién lo pide.
# Aquí solo están las rutas y su documentación. La lógica está en services.py, las validaciones
# en helpers.py, las consultas en queries.py y los errores (mensajes y ejemplos /docs) en errors.py.
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.deps import get_current_user, require_permiso
from app.core.docs import ERROR_401
from app.modulos.estadisticas import services
from app.modulos.estadisticas.errors import DOC_403_RESUMEN, DOC_422_RESUMEN
from app.modulos.estadisticas.helpers import Filtros
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
Devuelve el panel de estadísticas del usuario de la sesión. La forma es la misma para los 4 roles; el contenido depende del rol.

**Permiso requerido:** `estadisticas_view`. El rol `admin` siempre tiene acceso. Requiere `Authorization: Bearer <token>`.

**Parámetros (todos opcionales):**
- `fecha_inicio` y `fecha_fin` (`AAAA-MM-DD`): periodo por **fecha de emisión**, ambos días incluidos. Sin ninguna: el **mes actual**.
  Solo `fecha_inicio`: hasta el fin de ese mes. Solo `fecha_fin`: desde el inicio de ese mes. El aplicado viene en `periodo`.
- Filtros que acepta cada rol (los demás **se ignoran**, porque el alcance sale del token):

| Rol | Filtros | Valores de `estado` |
|---|---|---|
| `admin` | `empresa_id`, `estado` | de la **empresa**: `todas`, `activa`, `pendiente`, `suspendida`, `rechazada` |
| `empresa` | `bodega_id` (**403** si no es suya), `bodeguero_id`, `tipo_id` | — |
| `bodeguero` y roles personalizados | `tipo_id`, `estado` | `todas`, `pendientes`, `completadas`, `rechazadas` |
| `cliente` | `empresa_id`, `estado` | `todas`, `pendientes`, `aceptadas`, `rechazadas` |

**Qué facturas cuenta (la misma regla de `GET /facturas`):**
- `admin`: todas. `empresa`: las de su empresa. Bodeguero: solo las que creó.
- `cliente`: las que son para él, nunca las `emitida` (son borradores que no ve).

**Qué devuelve cada rol:**

| Rol | `kpis` | `desglose_principal` (claves de cada fila) |
|---|---|---|
| `admin` | `empresas_activas`, `empresas_pendientes`, `clientes_globales`, `tasa_entrega_global` | `nombre`, `bodegas`, `facturas`, `rechazadas`, `efectividad` (10 empresas) |
| `empresa` | `total_facturas`, `pendientes_cierre`, `tasa_aceptacion`, `tasa_rechazo` | `nombre`, `emitidas`, `completadas`, `rechazadas`, `efectividad` |
| bodeguero | `por_despachar`, `sin_firma`, `completadas`, `rechazadas` | `nombre`, `emitidas`, `completadas`, `rechazadas` |
| `cliente` | `pendientes_accion`, `recibidas_total`, `rechazadas_total`, `empresas_proveedoras` | `nombre`, `total_facturas`, `aceptadas`, `rechazadas` |

**Reglas de los números:**
- `completadas` = `firmada` + `recibida`. `pendientes` = `emitida` + `entregada`. En las tablas, `emitidas` es el **total** de facturas.
- Las tasas y la efectividad son sobre el total de facturas, con 1 decimal.
- Todo depende del periodo y los filtros, salvo `empresas_activas`, `empresas_pendientes`, `clientes_globales`, `filtros_disponibles`
  y la cantidad de `bodegas`, que son el total actual.
- `alerta`: `empresas_pendientes` y `pendientes_cierre` si son mayores que 0; `tasa_rechazo` si pasa del 10 %.
- `serie_temporal` va día por día si el periodo es de hasta 62 días; si es más largo, mes por mes (con el primer día del mes).
- `alertas_detalle`: las últimas 5 rechazadas, para empresa y bodeguero.

**En desuso** (siguen igual hasta que el frontend confirme): `desde`, `hasta`, `tarjetas` y `series`, que no usan los filtros nuevos.
""",
    response_description="Periodo, filtros disponibles, tarjetas, tabla, serie por fecha y alertas",
    responses={401: ERROR_401, 403: DOC_403_RESUMEN, 422: DOC_422_RESUMEN},
)
def resumen(
    fecha_inicio: date | None = Query(None, description="Primer día del periodo (AAAA-MM-DD). Por defecto, el inicio del mes."),
    fecha_fin: date | None = Query(None, description="Último día del periodo (AAAA-MM-DD). Por defecto, el fin del mes."),
    empresa_id: int | None = Query(None, description="Admin: una empresa. Cliente: una de las que le han facturado. A los demás se les ignora."),
    bodega_id: int | None = Query(None, description="Solo empresa: una de sus bodegas (403 si no lo es). A los demás se les ignora."),
    bodeguero_id: int | None = Query(None, description="Solo empresa: las facturas que creó ese usuario. A los demás se les ignora."),
    tipo_id: int | None = Query(None, description="Empresa y bodeguero: facturas con ese tipo de producto. A los demás se les ignora."),
    estado: str | None = Query(None, description="Admin: estado de la empresa. Bodeguero y cliente: grupo de estados. A la empresa se le ignora."),
    desde: date | None = Query(None, deprecated=True, description="**En desuso:** usar `fecha_inicio`."),
    hasta: date | None = Query(None, deprecated=True, description="**En desuso:** usar `fecha_fin`."),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(puede_ver),
):
    """Panel de estadísticas según el rol del usuario."""
    filtros = Filtros(empresa_id=empresa_id, bodega_id=bodega_id, bodeguero_id=bodeguero_id, tipo_id=tipo_id, estado=estado)
    return services.resumen(db, usuario, fecha_inicio, fecha_fin, desde, hasta, filtros)
