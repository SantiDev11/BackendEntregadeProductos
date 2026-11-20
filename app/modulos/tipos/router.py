# Endpoints de Tipos. Cada tipo pertenece a una bodega (catálogo por bodega).
# Aquí solo están las rutas y su documentación. La lógica está en services.py, las validaciones
# en helpers.py, las consultas en queries.py y los errores (mensajes y ejemplos /docs) en errors.py.
from fastapi import APIRouter, Depends, Path, Query, Response, status
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.deps import get_current_user, require_permiso
from app.core.docs import ERROR_401
from app.modulos.tipos.schemas import TipoCreate, TipoUpdate, TipoOut, TipoPaginado
from app.modulos.usuarios.models import Usuario
from app.modulos.tipos import services
from app.modulos.tipos.errors import (DOC_404, DOC_403_TIPO, DOC_422_ID, DOC_403_LISTAR, DOC_422_LISTAR, DOC_400_CREAR,
                                      DOC_422_CREAR, DOC_400_ACTUALIZAR, DOC_422_ACTUALIZAR, DOC_400_ELIMINAR)

# Permiso que exige cada acción (los permisos se leen de la BD en cada petición; el rol admin siempre pasa)
puede_ver = require_permiso("tipos_view")
puede_crear = require_permiso("tipos_create")
puede_editar = require_permiso("tipos_edit")
puede_eliminar = require_permiso("tipos_delete")

# Todos los endpoints exigen sesión; cada uno exige además su permiso (ver arriba)
router = APIRouter(
    prefix="/tipos",
    tags=["Tipos"],
    dependencies=[Depends(get_current_user)],
)

ALCANCE = ("**Alcance:** el `admin` maneja todos los tipos. Cualquier otro usuario solo los de **sus bodegas** "
           "(las que tienen `bodeguero_id` = su id).")


# ===== CONSULTAS (GET) =====

@router.get(
    "",
    response_model=TipoPaginado,
    summary="Listar tipos",
    description=f"""
Devuelve los tipos en páginas, con búsqueda por nombre y filtros por estado y bodega.

**Permiso requerido:** `tipos_view`. El rol `admin` siempre tiene acceso. Requiere `Authorization: Bearer <token>`.

{ALCANCE}

**Parámetros (todos opcionales):**
- `q`: busca tipos cuyo nombre **contenga** el texto, sin distinguir mayúsculas (`ali` encuentra "Alimentos").
- `estado`: `true` solo activos, `false` solo inactivos. Si no se envía, devuelve todos.
- `bodega_id`: solo los tipos de esa bodega. **Admin:** si no lo envía, ve todos (incluidos los que no tienen bodega).
  **Otros usuarios:** siempre ven solo los de sus bodegas; si envían una bodega que no es suya, la lista sale vacía.
- `page`: número de página, empieza en 1.
- `limit`: elementos por página, por defecto 10 y máximo 100.

**Reglas:**
- Los resultados se ordenan por `id`.
- `total` es la cantidad que cumple los filtros, no solo la de la página actual.
- Cada tipo trae `bodega_id` y `bodega_nombre` (o `null` si no tiene bodega).

**Devuelve:** `{{"data": [...], "total": n, "page": p, "limit": l}}`.
""",
    response_description="Página de tipos con el total que cumple los filtros",
    responses={
        401: ERROR_401,
        403: DOC_403_LISTAR,
        422: DOC_422_LISTAR,
    },
)
def listar_tipos(
    q: str | None = Query(None, description="Texto a buscar en el nombre (contiene, sin distinguir mayúsculas)."),
    estado: bool | None = Query(None, description="Filtra por estado: `true` activos, `false` inactivos. Si no se envía, devuelve todos."),
    bodega_id: int | None = Query(None, description="Filtra por bodega. Los usuarios que no son admin solo ven las suyas."),
    page: int = Query(1, ge=1, description="Número de página. Empieza en 1."),
    limit: int = Query(10, ge=1, le=100, description="Elementos por página. Por defecto 10, máximo 100."),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(puede_ver),
):
    """Lista los tipos con búsqueda, filtros y paginación. Quien no es admin solo ve los de sus bodegas."""
    return services.listar_tipos(q, estado, bodega_id, page, limit, db, usuario)


@router.get(
    "/{tipo_id}",
    response_model=TipoOut,
    summary="Obtener un tipo",
    description=f"""
Devuelve un tipo por su id, con su bodega, su estado y sus datos de auditoría.

**Permiso requerido:** `tipos_view`. El rol `admin` siempre tiene acceso. Requiere `Authorization: Bearer <token>`.

{ALCANCE} Un tipo de otra bodega responde 403.

**Parámetros:**
- `tipo_id` (en la ruta): id del tipo.

**Devuelve:** el tipo, 404 si no existe o 403 si es de otra bodega.
""",
    response_description="El tipo encontrado",
    responses={401: ERROR_401, 403: DOC_403_TIPO, 404: DOC_404, 422: DOC_422_ID},
)
def obtener_tipo(
    tipo_id: int = Path(description="Id del tipo.", examples=[1]),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(puede_ver),
):
    """Devuelve un tipo por su id (si es de una de las bodegas del usuario, o si es admin)."""
    return services.obtener_tipo(tipo_id, db, usuario)


# ===== CREAR (POST) =====

@router.post(
    "",
    response_model=TipoOut,
    status_code=status.HTTP_201_CREATED,
    summary="Crear un tipo",
    description="""
Crea un tipo nuevo en una bodega.

**Permiso requerido:** `tipos_create`. El rol `admin` siempre tiene acceso. Requiere `Authorization: Bearer <token>`.

**Cuerpo:**
- `nombre` (**obligatorio**): de 1 a 100 caracteres. Se quitan los espacios al inicio y al final.
- `bodega_id`: ver las reglas.
- `estado` (opcional): por defecto `true` (activo).

**A qué bodega va:**
- **Admin:** a la `bodega_id` que envíe (debe existir). Si no la envía, el tipo queda sin bodega.
- **Otro usuario con una sola bodega:** a su bodega, **sin importar** lo que venga en `bodega_id`.
- **Otro usuario con varias bodegas:** debe enviar `bodega_id` con una de las suyas.
- **Otro usuario sin bodegas:** 400.

**Reglas:**
- El nombre debe ser único **dentro de la bodega**, sin distinguir mayúsculas: "Arroz" puede estar en la bodega 1 y en la 2,
  pero no dos veces en la misma.
- `creado_por`, `actualizado_por`, `creado_en` y `actualizado_en` los pone el servidor.

**Devuelve:** 201 con el tipo creado (incluye `bodega_id` y `bodega_nombre`).
""",
    response_description="El tipo creado, con su bodega y datos de auditoría",
    responses={
        400: DOC_400_CREAR,
        401: ERROR_401,
        403: DOC_403_LISTAR,
        422: DOC_422_CREAR,
    },
)
def crear_tipo(
    datos: TipoCreate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(puede_crear),
):
    """Crea un tipo en la bodega que corresponde y registra quién lo creó."""
    return services.crear_tipo(datos, db, usuario)


# ===== EDITAR (PUT) =====

@router.put(
    "/{tipo_id}",
    response_model=TipoOut,
    summary="Editar un tipo",
    description=f"""
Actualiza un tipo existente. **Solo cambia los campos que se envían.**

**Permiso requerido:** `tipos_edit`. El rol `admin` siempre tiene acceso. Requiere `Authorization: Bearer <token>`.

{ALCANCE} Un tipo de otra bodega responde 403.

**Parámetros:**
- `tipo_id` (en la ruta): id del tipo a editar.

**Cuerpo (todos opcionales):**
- `nombre`: nuevo nombre, de 1 a 100 caracteres.
- `bodega_id`: **solo admin**, mueve el tipo a otra bodega (debe existir). Si lo envía otro usuario, se ignora.
- `estado`: `true` para activar, `false` para desactivar.

**Reglas:**
- Un campo que no se envía, o que llega en `null`, no se cambia.
- El nombre no puede repetirse **dentro de la bodega** del tipo (sin distinguir mayúsculas). Volver a enviar su mismo nombre no es error.
- El servidor guarda en `actualizado_por` el id del usuario que hace el cambio y actualiza `actualizado_en`.

**Devuelve:** el tipo actualizado.
""",
    response_description="El tipo con los cambios aplicados",
    responses={
        400: DOC_400_ACTUALIZAR,
        401: ERROR_401,
        403: DOC_403_TIPO,
        404: DOC_404,
        422: DOC_422_ACTUALIZAR,
    },
)
def actualizar_tipo(
    datos: TipoUpdate,
    tipo_id: int = Path(description="Id del tipo a editar.", examples=[1]),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(puede_editar),
):
    """Actualiza solo los campos enviados (los que lleguen en null se ignoran)
    y registra quién hizo el cambio."""
    return services.actualizar_tipo(datos, tipo_id, db, usuario)


# ===== ELIMINAR (DELETE) =====

@router.delete(
    "/{tipo_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar un tipo",
    description=f"""
Elimina un tipo de forma **definitiva** (no es un borrado lógico).

**Permiso requerido:** `tipos_delete`. El rol `admin` siempre tiene acceso. Requiere `Authorization: Bearer <token>`.

{ALCANCE} Un tipo de otra bodega responde 403.

**Parámetros:**
- `tipo_id` (en la ruta): id del tipo a eliminar.

**Reglas:**
- Si el tipo está usado en alguna factura, no se elimina y responde 400.
- Para desactivar un tipo sin borrarlo, usa `PUT` con `{{"estado": false}}`.

**Devuelve:** 204 **sin cuerpo**.
""",
    response_description="Tipo eliminado. La respuesta no tiene cuerpo",
    responses={
        400: DOC_400_ELIMINAR,
        401: ERROR_401, 403: DOC_403_TIPO, 404: DOC_404, 422: DOC_422_ID,
    },
)
def eliminar_tipo(
    tipo_id: int = Path(description="Id del tipo a eliminar.", examples=[1]),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(puede_eliminar),
):
    """Elimina un tipo (si es de una de las bodegas del usuario, o si es admin). Responde 204 sin cuerpo."""
    services.eliminar_tipo(tipo_id, db, usuario)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
