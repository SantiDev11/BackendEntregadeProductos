# Endpoints de Permisos. Las consultas a la BD están en queries.py y las validaciones en helpers.py.
from fastapi import APIRouter, Depends, Path, Query, Response, status
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.deps import get_current_user, no_empresa, require_permiso
from app.core.docs import ERROR_401, ERROR_403
from app.modulos.permisos.schemas import PermisoCreate, PermisoUpdate, PermisoOut, PermisoPaginado
from app.modulos.usuarios.models import Usuario
from app.modulos.permisos import services
from app.modulos.permisos.errors import (DOC_404, DOC_400_DUPLICADO, DOC_422_ID, DOC_422_LISTAR, DOC_422_CREAR,
                                         DOC_422_ACTUALIZAR, DOC_400_ELIMINAR)

# Permiso que exige cada acción (los permisos se leen de la BD en cada petición; el rol admin siempre pasa)
puede_ver = require_permiso("permisos_view")
puede_crear = require_permiso("permisos_create")
puede_editar = require_permiso("permisos_edit")
puede_eliminar = require_permiso("permisos_delete")

# Todos los endpoints exigen sesión; cada uno exige además su permiso (ver arriba). El rol empresa no entra a ninguno.
router = APIRouter(
    prefix="/permisos",
    tags=["Permisos"],
    dependencies=[Depends(get_current_user), Depends(no_empresa)],
)


# ===== CONSULTAS (GET) =====

@router.get(
    "",
    response_model=PermisoPaginado,
    summary="Listar permisos",
    description="""
Devuelve los permisos en páginas, con búsqueda por nombre y filtro por estado.

**Permiso requerido:** `permisos_view`. El rol `admin` siempre tiene acceso. Requiere `Authorization: Bearer <token>`.

**Parámetros (todos opcionales):**
- `q`: busca permisos cuyo nombre **contenga** el texto, sin distinguir mayúsculas (`orden` encuentra "crear_orden").
- `estado`: `true` solo activos, `false` solo inactivos. Si no se envía, devuelve todos.
- `page`: número de página, empieza en 1.
- `limit`: elementos por página, por defecto 10 y máximo 100.

**Reglas:**
- Los resultados se ordenan por `id`.
- `total` es la cantidad que cumple el filtro, no solo la de la página actual.

**Devuelve:** `{"data": [...], "total": n, "page": p, "limit": l}`.
""",
    response_description="Página de permisos con el total que cumple el filtro",
    responses={
        401: ERROR_401,
        403: ERROR_403,
        422: DOC_422_LISTAR,
    },
)
def listar_permisos(
    q: str | None = Query(None, description="Texto a buscar en el nombre (contiene, sin distinguir mayúsculas)."),
    estado: bool | None = Query(None, description="Filtra por estado: `true` activos, `false` inactivos. Si no se envía, devuelve todos."),
    page: int = Query(1, ge=1, description="Número de página. Empieza en 1."),
    limit: int = Query(10, ge=1, le=100, description="Elementos por página. Por defecto 10, máximo 100."),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(puede_ver),
):
    """Lista los permisos con búsqueda por nombre, filtro por estado y paginación."""
    return services.listar_permisos(q, estado, page, limit, db, usuario)


@router.get(
    "/{permiso_id}",
    response_model=PermisoOut,
    summary="Obtener un permiso",
    description="""
Devuelve un permiso por su id, con su estado y sus datos de auditoría.

**Permiso requerido:** `permisos_view`. El rol `admin` siempre tiene acceso. Requiere `Authorization: Bearer <token>`.

**Parámetros:**
- `permiso_id` (en la ruta): id del permiso.

**Devuelve:** el permiso, o 404 si no existe.
""",
    response_description="El permiso encontrado",
    responses={401: ERROR_401, 403: ERROR_403, 404: DOC_404, 422: DOC_422_ID},
)
def obtener_permiso(
    permiso_id: int = Path(description="Id del permiso.", examples=[1]),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(puede_ver),
):
    """Devuelve un permiso por su id."""
    return services.obtener_permiso(permiso_id, db, usuario)


# ===== CREAR (POST) =====

@router.post(
    "",
    response_model=PermisoOut,
    status_code=status.HTTP_201_CREATED,
    summary="Crear un permiso",
    description="""
Crea un permiso nuevo.

**Permiso requerido:** `permisos_create`. El rol `admin` siempre tiene acceso. Requiere `Authorization: Bearer <token>`.

**Cuerpo:**
- `nombre` (**obligatorio**): de 1 a 100 caracteres. Se quitan los espacios al inicio y al final.
- `descripcion` (opcional): hasta 255 caracteres. Si no se envía, queda en `null`.
- `estado` (opcional): por defecto `true` (activo).

**Reglas:**
- El nombre debe ser único **sin distinguir mayúsculas**: si ya existe "crear_orden", "CREAR_ORDEN" da 400.
- `creado_por`, `actualizado_por`, `creado_en` y `actualizado_en` los pone el servidor.
  Si se envían en el cuerpo, se ignoran.

**Devuelve:** 201 con el permiso creado.
""",
    response_description="El permiso creado, con su id y datos de auditoría",
    responses={
        400: DOC_400_DUPLICADO,
        401: ERROR_401,
        403: ERROR_403,
        422: DOC_422_CREAR,
    },
)
def crear_permiso(
    datos: PermisoCreate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(puede_crear),
):
    """Crea un permiso nuevo y registra quién lo creó."""
    return services.crear_permiso(datos, db, usuario)


# ===== EDITAR (PUT) =====

@router.put(
    "/{permiso_id}",
    response_model=PermisoOut,
    summary="Editar un permiso",
    description="""
Actualiza un permiso existente. **Solo cambia los campos que se envían.**

**Permiso requerido:** `permisos_edit`. El rol `admin` siempre tiene acceso. Requiere `Authorization: Bearer <token>`.

**Parámetros:**
- `permiso_id` (en la ruta): id del permiso a editar.

**Cuerpo (todos opcionales):**
- `nombre`: nuevo nombre, de 1 a 100 caracteres.
- `descripcion`: nueva descripción, hasta 255 caracteres. Para **borrarla** se envía `""` (cadena vacía).
- `estado`: `true` para activar, `false` para desactivar.

**Reglas:**
- Un campo que no se envía, o que llega en `null`, no se cambia.
- El nombre no puede ser igual al de **otro** permiso (sin distinguir mayúsculas). Volver a enviar el mismo nombre del permiso no es error.
- El servidor guarda en `actualizado_por` el id del usuario que hace el cambio y actualiza `actualizado_en`.
  `creado_por` y `creado_en` no cambian.

**Devuelve:** el permiso actualizado.
""",
    response_description="El permiso con los cambios aplicados",
    responses={
        400: DOC_400_DUPLICADO,
        401: ERROR_401,
        403: ERROR_403,
        404: DOC_404,
        422: DOC_422_ACTUALIZAR,
    },
)
def actualizar_permiso(
    datos: PermisoUpdate,
    permiso_id: int = Path(description="Id del permiso a editar.", examples=[1]),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(puede_editar),
):
    """Actualiza solo los campos enviados (los que lleguen en null se ignoran)
    y registra quién hizo el cambio. Para borrar la descripción se envía "" (cadena vacía)."""
    return services.actualizar_permiso(datos, permiso_id, db, usuario)


# ===== ELIMINAR (DELETE) =====

@router.delete(
    "/{permiso_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar un permiso",
    description="""
Elimina un permiso de forma **definitiva** (no es un borrado lógico).

**Permiso requerido:** `permisos_delete`. El rol `admin` siempre tiene acceso. Requiere `Authorization: Bearer <token>`.

**Parámetros:**
- `permiso_id` (en la ruta): id del permiso a eliminar.

**Reglas:**
- Si el permiso está **asignado a uno o más roles** (plantilla) o a **uno o más usuarios**, no se elimina
  y responde 400. Primero hay que quitarlo de esos roles o usuarios.
- Para desactivar un permiso sin borrarlo, usa `PUT` con `{"estado": false}`.

**Devuelve:** 204 **sin cuerpo**.
""",
    response_description="Permiso eliminado. La respuesta no tiene cuerpo",
    responses={
        400: DOC_400_ELIMINAR,
        401: ERROR_401,
        403: ERROR_403,
        404: DOC_404,
        422: DOC_422_ID,
    },
)
def eliminar_permiso(
    permiso_id: int = Path(description="Id del permiso a eliminar.", examples=[1]),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(puede_eliminar),
):
    """Elimina un permiso si no está asignado a ningún rol. Responde 204 sin cuerpo."""
    services.eliminar_permiso(permiso_id, db, usuario)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
