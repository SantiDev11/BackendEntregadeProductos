# Endpoints de Roles. Las consultas a la BD están en queries.py y las validaciones en helpers.py.
from fastapi import APIRouter, Depends, Path, Query, Response, status
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.deps import get_current_user, no_empresa, require_permiso
from app.core.docs import ERROR_401, ERROR_403
from app.modulos.roles.schemas import RolCreate, RolEstadoUpdate, RolUpdate, RolPermisosUpdate, RolOut, RolPaginado
from app.modulos.usuarios.models import Usuario
from app.modulos.roles import services
from app.modulos.roles.errors import (DOC_404, DOC_400_DUPLICADO, DOC_422_ID, DOC_422_LISTAR, DOC_422_CREAR,
                                      DOC_422_ACTUALIZAR, DOC_400_ASIGNAR, DOC_422_ASIGNAR, DOC_400_ELIMINAR,
                                      DOC_400_ESTADO, DOC_422_ESTADO)

# Permiso que exige cada acción (los permisos se leen de la BD en cada petición; el rol admin siempre pasa)
puede_ver = require_permiso("roles_view")
puede_crear = require_permiso("roles_create")
puede_editar = require_permiso("roles_edit")
puede_eliminar = require_permiso("roles_delete")

# Todos los endpoints exigen sesión; cada uno exige además su permiso (ver arriba). El rol empresa no entra a ninguno.
router = APIRouter(
    prefix="/roles",
    tags=["Roles"],
    dependencies=[Depends(get_current_user), Depends(no_empresa)],
)


# ===== CONSULTAS (GET) =====

@router.get(
    "",
    response_model=RolPaginado,
    summary="Listar roles",
    description="""
Devuelve los roles en páginas, cada uno con su lista de permisos, con búsqueda por nombre y filtro por estado.

**Permiso requerido:** `roles_view`. El rol `admin` siempre tiene acceso. Requiere `Authorization: Bearer <token>`.

**Parámetros (todos opcionales):**
- `q`: busca roles cuyo nombre **contenga** el texto, sin distinguir mayúsculas (`bode` encuentra "bodeguero").
- `estado`: `true` solo activos, `false` solo inactivos. Si no se envía, devuelve todos.
- `page`: número de página, empieza en 1.
- `limit`: elementos por página, por defecto 10 y máximo 100.

**Reglas:**
- Los resultados se ordenan por `id`.
- `total` es la cantidad que cumple el filtro, no solo la de la página actual.
- Cada rol trae `permisos` con `id` y `nombre` (lista vacía si no tiene).

**Devuelve:** `{"data": [...], "total": n, "page": p, "limit": l}`.
""",
    response_description="Página de roles, cada uno con sus permisos, y el total que cumple el filtro",
    responses={
        401: ERROR_401,
        403: ERROR_403,
        422: DOC_422_LISTAR,
    },
)
def listar_roles(
    q: str | None = Query(None, description="Texto a buscar en el nombre (contiene, sin distinguir mayúsculas)."),
    estado: bool | None = Query(None, description="Filtra por estado: `true` activos, `false` inactivos. Si no se envía, devuelve todos."),
    page: int = Query(1, ge=1, description="Número de página. Empieza en 1."),
    limit: int = Query(10, ge=1, le=100, description="Elementos por página. Por defecto 10, máximo 100."),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(puede_ver),
):
    """Lista los roles (con sus permisos) con búsqueda por nombre, filtro por estado y paginación."""
    return services.listar_roles(q, estado, page, limit, db, usuario)


@router.get(
    "/{rol_id}",
    response_model=RolOut,
    summary="Obtener un rol",
    description="""
Devuelve un rol por su id, con sus permisos, su estado y sus datos de auditoría.

**Permiso requerido:** `roles_view`. El rol `admin` siempre tiene acceso. Requiere `Authorization: Bearer <token>`.

**Parámetros:**
- `rol_id` (en la ruta): id del rol.

**Devuelve:** el rol con `permisos` (lista vacía si no tiene), o 404 si no existe.
""",
    response_description="El rol encontrado, con sus permisos",
    responses={401: ERROR_401, 403: ERROR_403, 404: DOC_404, 422: DOC_422_ID},
)
def obtener_rol(
    rol_id: int = Path(description="Id del rol.", examples=[1]),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(puede_ver),
):
    """Devuelve un rol por su id."""
    return services.obtener_rol(rol_id, db, usuario)


# ===== CREAR (POST) =====

@router.post(
    "",
    response_model=RolOut,
    status_code=status.HTTP_201_CREATED,
    summary="Crear un rol",
    description="""
Crea un rol nuevo **sin permisos**. Los permisos se asignan después con `PUT /roles/{rol_id}/permisos`.

**Permiso requerido:** `roles_create`. El rol `admin` siempre tiene acceso. Requiere `Authorization: Bearer <token>`.

**Cuerpo:**
- `nombre` (**obligatorio**): de 1 a 50 caracteres. Se quitan los espacios al inicio y al final.
- `descripcion` (opcional): hasta 255 caracteres. Si no se envía, queda en `null`.
- `estado` (opcional): por defecto `true` (activo).

**Reglas:**
- El nombre debe ser único **sin distinguir mayúsculas**: si ya existe "supervisor", "SUPERVISOR" da 400.
- `creado_por`, `actualizado_por`, `creado_en` y `actualizado_en` los pone el servidor.
  Si se envían en el cuerpo, se ignoran.

**Devuelve:** 201 con el rol creado y `permisos: []`.
""",
    response_description="El rol creado, con su id, datos de auditoría y sin permisos",
    responses={
        400: DOC_400_DUPLICADO,
        401: ERROR_401,
        403: ERROR_403,
        422: DOC_422_CREAR,
    },
)
def crear_rol(
    datos: RolCreate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(puede_crear),
):
    """Crea un rol nuevo (sin permisos) y registra quién lo creó."""
    return services.crear_rol(datos, db, usuario)


# ===== EDITAR (PUT) =====

@router.put(
    "/{rol_id}",
    response_model=RolOut,
    summary="Editar un rol",
    description="""
Actualiza los datos de un rol existente. **Solo cambia los campos que se envían.**
Para cambiar sus permisos se usa `PUT /roles/{rol_id}/permisos`.

**Permiso requerido:** `roles_edit`. El rol `admin` siempre tiene acceso. Requiere `Authorization: Bearer <token>`.

**Parámetros:**
- `rol_id` (en la ruta): id del rol a editar.

**Cuerpo (todos opcionales):**
- `nombre`: nuevo nombre, de 1 a 50 caracteres.
- `descripcion`: nueva descripción, hasta 255 caracteres. Para **borrarla** se envía `""` (cadena vacía).
- `estado`: `true` para activar, `false` para desactivar.

**Reglas:**
- Un campo que no se envía, o que llega en `null`, no se cambia.
- El nombre no puede ser igual al de **otro** rol (sin distinguir mayúsculas). Volver a enviar el mismo nombre del rol no es error.
- Solo el `admin` puede cambiarle el nombre a un rol base (`admin`, `bodeguero`, `empresa`, `cliente`): los demás reciben 403.
- El servidor guarda en `actualizado_por` el id del usuario que hace el cambio y actualiza `actualizado_en`.
  `creado_por` y `creado_en` no cambian.

**Devuelve:** el rol actualizado, con sus permisos.
""",
    response_description="El rol con los cambios aplicados",
    responses={
        400: DOC_400_DUPLICADO,
        401: ERROR_401,
        403: ERROR_403,
        404: DOC_404,
        422: DOC_422_ACTUALIZAR,
    },
)
def actualizar_rol(
    datos: RolUpdate,
    rol_id: int = Path(description="Id del rol a editar.", examples=[1]),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(puede_editar),
):
    """Actualiza solo los campos enviados (los que lleguen en null se ignoran)
    y registra quién hizo el cambio. Para borrar la descripción se envía "" (cadena vacía)."""
    return services.actualizar_rol(datos, rol_id, db, usuario)


@router.patch(
    "/{rol_id}/estado",
    response_model=RolOut,
    summary="Activar o desactivar el rol",
    description=f"""
Activa o desactiva el rol sin tocar sus demás datos. Es lo mismo que enviar solo `estado` al `PUT`.

**Permiso requerido:** `roles_edit`. El rol `admin` siempre tiene acceso. Requiere `Authorization: Bearer <token>`.

**Cuerpo:** `{{"estado": false}}` para desactivar o `{{"estado": true}}` para activar.
- `estado` es **obligatorio** y debe ser `true` o `false` del JSON: `"true"`, `1` o `null` dan 422 `estado: debe ser true o false`.
- Repetir el mismo estado no es error.

**Reglas:**
- Un rol inactivo **no se puede asignar** al crear o editar usuarios (400 `El rol indicado no está activo`).
  Los usuarios que ya lo tienen siguen igual.
- Los roles base (`admin`, `empresa`, `bodeguero` y `cliente`) **no se pueden desactivar** (400).
- El rol `empresa` no entra a este módulo (403).
- Guarda en `actualizado_por` quién hizo el cambio.

**Devuelve:** el rol con su nuevo estado.
""",
    response_description="El rol con su nuevo estado",
    responses={
        400: DOC_400_ESTADO,
        401: ERROR_401,
        403: ERROR_403,
        404: DOC_404,
        422: DOC_422_ESTADO,
    },
)
def cambiar_estado_rol(
    datos: RolEstadoUpdate,
    rol_id: int = Path(description="Id de el rol.", examples=[1]),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(puede_editar),
):
    """Activa o desactiva el rol, con las mismas reglas que al editarlo."""
    return services.cambiar_estado_rol(datos, rol_id, db, usuario)


@router.put(
    "/{rol_id}/permisos",
    response_model=RolOut,
    summary="Asignar permisos a un rol (plantilla)",
    description="""
**Reemplaza** todos los permisos **plantilla** de un rol por la lista enviada.

> **Importante:** los permisos del rol son solo una **plantilla**. Se copian a cada usuario **nuevo** que se crea con ese rol.
> Cambiarlos aquí **no** modifica los permisos de usuarios que ya existen.
> Para dar o quitar accesos a un usuario se usa `PUT /usuarios/{id}/permisos`.

**Permiso requerido:** `roles_edit`. El rol `admin` siempre tiene acceso. Requiere `Authorization: Bearer <token>`.

**Parámetros:**
- `rol_id` (en la ruta): id del rol.

**Cuerpo:**
- `permisos_ids` (**obligatorio**): lista con los ids de los permisos que tendrá el rol.

**Reglas:**
- No suma permisos: el rol queda **exactamente** con los de la lista. Los que no estén se le quitan.
- Una lista vacía `[]` le quita todos los permisos.
- Los ids repetidos se ignoran.
- Si **algún** id no existe, responde 400 y **no cambia nada**.
- El servidor guarda en `actualizado_por` el id del usuario que hace el cambio.

**Devuelve:** el rol actualizado con su nueva lista de permisos.
""",
    response_description="El rol con su nueva lista de permisos",
    responses={
        400: DOC_400_ASIGNAR,
        401: ERROR_401,
        403: ERROR_403,
        404: DOC_404,
        422: DOC_422_ASIGNAR,
    },
)
def asignar_permisos_rol(
    datos: RolPermisosUpdate,
    rol_id: int = Path(description="Id del rol al que se le asignan los permisos.", examples=[1]),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(puede_editar),
):
    """Reemplaza todos los permisos del rol por los de la lista (vacía = sin permisos)."""
    return services.asignar_permisos_rol(datos, rol_id, db, usuario)


# ===== ELIMINAR (DELETE) =====

@router.delete(
    "/{rol_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar un rol",
    description="""
Elimina un rol de forma **definitiva** (no es un borrado lógico), junto con sus asignaciones de permisos.

**Permiso requerido:** `roles_delete`. El rol `admin` siempre tiene acceso. Requiere `Authorization: Bearer <token>`.

**Parámetros:**
- `rol_id` (en la ruta): id del rol a eliminar.

**Reglas:**
- Si hay **usuarios con este rol**, no se elimina y responde 400. Primero hay que cambiarles el rol.
- Al eliminarlo se quitan sus filas de `rol_permiso`. Los permisos en sí **no** se borran.
- Para desactivar un rol sin borrarlo, usa `PUT` con `{"estado": false}`.

**Devuelve:** 204 **sin cuerpo**.
""",
    response_description="Rol eliminado. La respuesta no tiene cuerpo",
    responses={
        400: DOC_400_ELIMINAR,
        401: ERROR_401,
        403: ERROR_403,
        404: DOC_404,
        422: DOC_422_ID,
    },
)
def eliminar_rol(
    rol_id: int = Path(description="Id del rol a eliminar.", examples=[1]),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(puede_eliminar),
):
    """Elimina un rol si ningún usuario lo tiene. Responde 204 sin cuerpo."""
    services.eliminar_rol(rol_id, db, usuario)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
