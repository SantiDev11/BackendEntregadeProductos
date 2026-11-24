# Endpoints de Empresas: solo el rol admin (cualquier otro recibe 403, aunque tenga permisos asignados).
# Aquí solo están las rutas y su documentación. La lógica está en services.py, las validaciones
# en helpers.py, las consultas en queries.py y los errores (mensajes y ejemplos /docs) en errors.py.
from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.deps import require_roles
from app.core.docs import ERROR_401
from app.modulos.empresas import services
from app.modulos.empresas.errors import DOC_400_ESTADO, DOC_403, DOC_404, DOC_422_ESTADO, DOC_422_LISTAR
from app.modulos.empresas.schemas import EmpresaEstadoUpdate, EmpresaOut, EmpresaPaginado

router = APIRouter(
    prefix="/empresas",
    tags=["Empresas"],
    dependencies=[Depends(require_roles("admin"))],
)


# ===== CONSULTAS (GET) =====

@router.get(
    "",
    response_model=EmpresaPaginado,
    summary="Listar empresas",
    description="""
Devuelve las empresas en páginas, de la más reciente a la más antigua, con búsqueda y filtro por estado.

**Quién puede usarlo:** solo el rol `admin`. Requiere `Authorization: Bearer <token>`.

**Parámetros (todos opcionales):**
- `q`: busca en la razón social, el NIT o el correo (contiene, sin distinguir mayúsculas).
- `estado`: `pendiente`, `activa`, `rechazada` o `suspendida`. Si no se envía, devuelve todas.
- `page`: número de página, empieza en 1.
- `limit`: elementos por página, por defecto 10 y máximo 100.

**Devuelve:** `{"data": [...], "total": n, "page": p, "limit": l}`. Cada empresa trae sus totales de bodegueros, bodegas y facturas.
""",
    response_description="Página de empresas con el total que cumple los filtros",
    responses={401: ERROR_401, 403: DOC_403, 422: DOC_422_LISTAR},
)
def listar_empresas(
    q: str | None = Query(None, description="Texto a buscar en la razón social, el NIT o el correo."),
    estado: str | None = Query(None, description="Filtra por estado: pendiente, activa, rechazada o suspendida."),
    page: int = Query(1, ge=1, description="Número de página. Empieza en 1."),
    limit: int = Query(10, ge=1, le=100, description="Elementos por página. Por defecto 10, máximo 100."),
    db: Session = Depends(get_db),
):
    """Lista las empresas con búsqueda, filtro por estado y paginación."""
    return services.listar(db, q=q, estado=estado, page=page, limit=limit)


# ===== CAMBIAR ESTADO (PATCH) =====

@router.patch(
    "/{empresa_id}/estado",
    response_model=EmpresaOut,
    summary="Aprobar, rechazar, suspender o reactivar una empresa",
    description="""
Cambia el estado de una empresa.

**Quién puede usarlo:** solo el rol `admin`. Requiere `Authorization: Bearer <token>`.

**Cuerpo:**
- `estado` (**obligatorio**): `activa`, `rechazada` o `suspendida`.
- `motivo_rechazo`: **obligatorio solo al rechazar**, de 10 a 255 caracteres. Con otro estado se ignora.

**Cambios permitidos** (cualquier otro da 400):
- `pendiente` → `activa` o `rechazada`
- `activa` → `suspendida`
- `suspendida` → `activa`
- `rechazada` → `activa`

**Reglas:**
- Al pasar a `activa` se borra el motivo de rechazo.
- Mientras no esté `activa`, **ninguno de sus usuarios** puede entrar (403), aunque tenga un token vigente.
- Sus bodegas y facturas no se borran.

**Devuelve:** la empresa con su nuevo estado.
""",
    response_description="La empresa con su nuevo estado",
    responses={400: DOC_400_ESTADO, 401: ERROR_401, 403: DOC_403, 404: DOC_404, 422: DOC_422_ESTADO},
)
def cambiar_estado_empresa(
    datos: EmpresaEstadoUpdate,
    empresa_id: int = Path(description="Id de la empresa.", examples=[1]),
    db: Session = Depends(get_db),
):
    """Aprueba, rechaza, suspende o reactiva una empresa."""
    return services.cambiar_estado(db, empresa_id, datos)
