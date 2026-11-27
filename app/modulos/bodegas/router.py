# Endpoints de Bodegas: solo las rutas y su documentación.
# La lógica está en services.py, las validaciones en helpers.py, las consultas en queries.py
# y los errores (mensajes y ejemplos para /docs) en errors.py.
from fastapi import APIRouter, Depends, Path, Query, Response, status
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.alcance import Alcance, filtro_empresa
from app.core.deps import get_current_user, require_permiso
from app.core.docs import ERROR_401, ERROR_403
from app.modulos.bodegas import services
from app.modulos.bodegas.errors import (DOC_400_ACTUALIZAR, DOC_400_CREAR, DOC_400_ELIMINAR, DOC_404, DOC_422_CREAR,
                                        DOC_422_EDITAR, DOC_422_ESTADO, DOC_422_ID, DOC_422_LISTAR)
from app.modulos.bodegas.schemas import BodegaCreate, BodegaEstadoUpdate, BodegaUpdate, BodegaOut, BodegaPaginado
from app.modulos.usuarios.models import Usuario

# Permiso que exige cada acción (los permisos se leen de la BD en cada petición; el rol admin siempre pasa)
puede_ver = require_permiso("bodegas_view")
puede_crear = require_permiso("bodegas_create")
puede_editar = require_permiso("bodegas_edit")
puede_eliminar = require_permiso("bodegas_delete")

# Todos los endpoints exigen sesión; cada uno exige además su permiso (ver arriba)
router = APIRouter(
    prefix="/bodegas",
    tags=["Bodegas"],
    dependencies=[Depends(get_current_user)],
)


# ===== CONSULTAS (GET) =====

@router.get(
    "",
    response_model=BodegaPaginado,
    summary="Listar bodegas",
    description=f"""
Devuelve las bodegas en páginas, con búsqueda por nombre y filtros.

**Permiso requerido:** `bodegas_view`. El rol `admin` siempre tiene acceso. Requiere `Authorization: Bearer <token>`.

**Alcance:** el `admin` ve y maneja todas las bodegas (en el listado puede filtrar con `empresa_id`); una `empresa`, las de su empresa; cualquier otro usuario, solo las suyas (`bodeguero_id` = su id). Una bodega ajena le responde 404.

**Parámetros (todos opcionales):**
- `q`: busca bodegas cuyo nombre **contenga** el texto, sin distinguir mayúsculas (`central` encuentra "Bodega Central").
- `estado`: `true` solo activas, `false` solo inactivas. Si no se envía, devuelve todas.
- `bodeguero_id`: **solo admin**, para ver las bodegas de un bodeguero. Para el bodeguero se ignora: siempre ve las suyas.
- `page`: número de página, empieza en 1.
- `limit`: elementos por página, por defecto 10 y máximo 100.

**Reglas:**
- Los resultados se ordenan por `id`.
- `total` es la cantidad que cumple los filtros, no solo la de la página actual.
- Cada bodega trae `bodeguero_id` y `bodeguero_nombre` (su dueño, o `null`).

**Devuelve:** `{{"data": [...], "total": n, "page": p, "limit": l}}`.
""",
    response_description="Página de bodegas con el total que cumple los filtros",
    responses={
        401: ERROR_401,
        403: ERROR_403,
        422: DOC_422_LISTAR,
    },
)
def listar_bodegas(
    q: str | None = Query(None, description="Texto a buscar en el nombre (contiene, sin distinguir mayúsculas)."),
    estado: bool | None = Query(None, description="Filtra por estado: `true` activas, `false` inactivas. Si no se envía, devuelve todas."),
    bodeguero_id: int | None = Query(None, description="Solo admin: filtra por dueño. Para el bodeguero se ignora."),
    page: int = Query(1, ge=1, description="Número de página. Empieza en 1."),
    limit: int = Query(10, ge=1, le=100, description="Elementos por página. Por defecto 10, máximo 100."),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(puede_ver),
    alcance: Alcance = Depends(filtro_empresa),
):
    """Lista las bodegas con búsqueda, filtros y paginación. El bodeguero solo ve las suyas."""
    return services.listar(db, alcance, q=q, estado=estado, bodeguero_id=bodeguero_id, page=page, limit=limit)


@router.get(
    "/{bodega_id}",
    response_model=BodegaOut,
    summary="Obtener una bodega",
    description=f"""
Devuelve una bodega por su id, con su dueño, su estado y sus datos de auditoría.

**Permiso requerido:** `bodegas_view`. El rol `admin` siempre tiene acceso. Requiere `Authorization: Bearer <token>`.

**Alcance:** el `admin` ve y maneja todas las bodegas (en el listado puede filtrar con `empresa_id`); una `empresa`, las de su empresa; cualquier otro usuario, solo las suyas (`bodeguero_id` = su id). Una bodega ajena le responde 404.

**Parámetros:**
- `bodega_id` (en la ruta): id de la bodega.

**Devuelve:** la bodega, o 404 si no existe (o si es de otro bodeguero).
""",
    response_description="La bodega encontrada",
    responses={401: ERROR_401, 403: ERROR_403, 404: DOC_404, 422: DOC_422_ID},
)
def obtener_bodega(
    bodega_id: int = Path(description="Id de la bodega.", examples=[1]),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(puede_ver),
):
    """Devuelve una bodega por su id (el bodeguero solo las suyas)."""
    return services.obtener(db, bodega_id, usuario)


# ===== CREAR (POST) =====

@router.post(
    "",
    response_model=BodegaOut,
    status_code=status.HTTP_201_CREATED,
    summary="Crear una bodega",
    description="""
Crea una bodega nueva.

**Permiso requerido:** `bodegas_create`. El rol `admin` siempre tiene acceso. Requiere `Authorization: Bearer <token>`.

**Cuerpo (todos obligatorios, salvo `bodeguero_id` y `estado`):**
- `empresa_id` (**obligatorio para el admin**): id numérico de una empresa activa (ver `GET /empresas?estado=activa`).
- `nombre`: de 1 a 100 caracteres.
- `codigo`: código interno, hasta 30 caracteres.
- `direccion`: hasta 200 caracteres.
- `ciudad` y `departamento`: hasta 100 caracteres.
- `telefono`: **solo números**, de 7 a 15 dígitos. `correo`: formato de correo válido, hasta 100.
- Datos de quién recibe: `recibe_nombre` (100), `recibe_documento` (**letras y números**, hasta 30), `recibe_cargo` (100)
  y `recibe_telefono` (**solo números**, de 7 a 15 dígitos).
- `bodeguero_id` (opcional, **solo admin o empresa**): dueño de la bodega. Debe ser un número: `2`, no `"2"`.
- `estado` (opcional): por defecto `true` (activa).

**Reglas:**
- **Dueño:** si la crea un bodeguero, el dueño es él mismo y `bodeguero_id` se ignora.
  Si la crea el admin o una empresa, puede indicar `bodeguero_id` (un usuario con rol bodeguero) o dejarla sin dueño.
  El bodeguero debe ser de la empresa de la bodega; si no, da 400.
- **Empresa:** si la crea el admin y `empresa_id` falta, no es un número o no existe, da 422;
  si la empresa existe pero no está `activa`, da 400.
  Si la crea cualquier otro usuario, queda en la empresa **del token** y el `empresa_id` del cuerpo se **ignora**.
- El nombre debe ser único **sin distinguir mayúsculas**: si ya existe "Bodega Central", "bodega central" da 400.
- El `codigo` se guarda en **mayúsculas** y también debe ser único: "bod-01" choca con "BOD-01".
- Se quitan los espacios al inicio y al final. Un campo que falte, o que llegue vacío (`""` o solo espacios), da 422.
- `creado_por`, `actualizado_por`, `creado_en` y `actualizado_en` los pone el servidor.
  Si se envían en el cuerpo, se ignoran.

**Devuelve:** 201 con la bodega creada.
""",
    response_description="La bodega creada, con su id, su dueño y datos de auditoría",
    responses={
        400: DOC_400_CREAR,
        401: ERROR_401,
        403: ERROR_403,
        422: DOC_422_CREAR,
    },
)
def crear_bodega(
    datos: BodegaCreate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(puede_crear),
):
    """Crea una bodega nueva, define su dueño y registra quién la creó."""
    return services.crear(db, datos, usuario)


# ===== EDITAR (PUT) =====

@router.put(
    "/{bodega_id}",
    response_model=BodegaOut,
    summary="Editar una bodega",
    description=f"""
Actualiza una bodega existente. **Solo cambia los campos que se envían.**

**Permiso requerido:** `bodegas_edit`. El rol `admin` siempre tiene acceso. Requiere `Authorization: Bearer <token>`.

**Alcance:** el `admin` ve y maneja todas las bodegas (en el listado puede filtrar con `empresa_id`); una `empresa`, las de su empresa; cualquier otro usuario, solo las suyas (`bodeguero_id` = su id). Una bodega ajena le responde 404.

**Parámetros:**
- `bodega_id` (en la ruta): id de la bodega a editar.

**Cuerpo (se envían solo los que cambian):**
- `nombre`: nuevo nombre, de 1 a 100 caracteres.
- `codigo`, `direccion`, `ciudad`, `departamento`, `telefono`, `correo`: datos de la bodega.
- `recibe_nombre`, `recibe_documento`, `recibe_cargo`, `recibe_telefono`: datos de quién recibe.
- `telefono` y `recibe_telefono` solo aceptan **números** (7 a 15 dígitos); `recibe_documento`, letras y números.
- `bodeguero_id`: **solo admin**, para asignar o cambiar el dueño. Si lo envía un bodeguero, se ignora.
- `estado`: `true` para activar, `false` para desactivar.

**Reglas:**
- Un campo que no se envía, o que llega en `null`, no se cambia.
- Todos los datos de la bodega son obligatorios, así que **no se pueden borrar**: un `""` (o solo espacios) da 422
  `"campo: no puede estar vacío"`.
- El nombre no puede ser igual al de **otra** bodega (sin distinguir mayúsculas). Volver a enviar el mismo nombre de la bodega no es error.
- El `codigo` se guarda en mayúsculas y no puede tenerlo **otra** bodega.
- El servidor guarda en `actualizado_por` el id del usuario que hace el cambio y actualiza `actualizado_en`.
  `creado_por` y `creado_en` no cambian.

**Devuelve:** la bodega actualizada.
""",
    response_description="La bodega con los cambios aplicados",
    responses={
        400: DOC_400_ACTUALIZAR,
        401: ERROR_401,
        403: ERROR_403,
        404: DOC_404,
        422: DOC_422_EDITAR,
    },
)
def actualizar_bodega(
    datos: BodegaUpdate,
    bodega_id: int = Path(description="Id de la bodega a editar.", examples=[1]),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(puede_editar),
):
    """Actualiza solo los campos enviados y registra quién hizo el cambio."""
    return services.actualizar(db, bodega_id, datos, usuario)


@router.patch(
    "/{bodega_id}/estado",
    response_model=BodegaOut,
    summary="Activar o desactivar la bodega",
    description=f"""
Activa o desactiva la bodega sin tocar sus demás datos. Es lo mismo que enviar solo `estado` al `PUT`.

**Permiso requerido:** `bodegas_edit`. El rol `admin` siempre tiene acceso. Requiere `Authorization: Bearer <token>`.

**Cuerpo:** `{{"estado": false}}` para desactivar o `{{"estado": true}}` para activar.
- `estado` es **obligatorio** y debe ser `true` o `false` del JSON: `"true"`, `1` o `null` dan 422 `estado: debe ser true o false`.
- Repetir el mismo estado no es error.

**Reglas:**
- En una bodega inactiva **no se pueden crear facturas** (400). Sus facturas no cambian.
- Al desactivarla, sus tipos pasan a generales de su empresa (`bodega_id: null`, mismo `empresa_id`) y queda sin bodeguero
  (`bodeguero_id: null`). Ninguno se borra ni se desactiva. Al reactivarla no vuelven solos: se le asignan de nuevo.
- Si la desactiva su propio bodeguero, deja de ser suya: solo la empresa o el admin pueden reactivarla.
- Una `empresa` solo activa o desactiva **sus bodegas**; un bodeguero, las suyas. Otra bodega responde 404.
- Guarda en `actualizado_por` quién hizo el cambio.

**Devuelve:** la bodega con su nuevo estado.
""",
    response_description="La bodega con su nuevo estado",
    responses={
        401: ERROR_401,
        403: ERROR_403,
        404: DOC_404,
        422: DOC_422_ESTADO,
    },
)
def cambiar_estado_bodega(
    datos: BodegaEstadoUpdate,
    bodega_id: int = Path(description="Id de la bodega.", examples=[1]),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(puede_editar),
):
    """Activa o desactiva la bodega, con las mismas reglas que al editarlo."""
    return services.cambiar_estado(db, bodega_id, datos, usuario)


# ===== ELIMINAR (DELETE) =====

@router.delete(
    "/{bodega_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar una bodega",
    description=f"""
Elimina una bodega de forma **definitiva** (no es un borrado lógico).

**Permiso requerido:** `bodegas_delete`. El rol `admin` siempre tiene acceso. Requiere `Authorization: Bearer <token>`.

**Alcance:** el `admin` ve y maneja todas las bodegas (en el listado puede filtrar con `empresa_id`); una `empresa`, las de su empresa; cualquier otro usuario, solo las suyas (`bodeguero_id` = su id). Una bodega ajena le responde 404.

**Parámetros:**
- `bodega_id` (en la ruta): id de la bodega a eliminar.

**Reglas:**
- Si la bodega tiene facturas, no se elimina y responde 400: las facturas la necesitan. Se puede desactivar.
- Sus tipos **no** se borran ni se desactivan: pasan a generales de su empresa (`bodega_id: null`, mismo `empresa_id`),
  a la espera de otra bodega.
- Su bodeguero **no** se borra ni se desactiva: solo queda sin esta bodega.
- Para desactivar una bodega sin borrarla, usa `PATCH /bodegas/{{id}}/estado` con `{{"estado": false}}`.

**Devuelve:** 204 **sin cuerpo**.
""",
    response_description="Bodega eliminada. La respuesta no tiene cuerpo",
    responses={
        400: DOC_400_ELIMINAR,
        401: ERROR_401, 403: ERROR_403, 404: DOC_404, 422: DOC_422_ID,
    },
)
def eliminar_bodega(
    bodega_id: int = Path(description="Id de la bodega a eliminar.", examples=[1]),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(puede_eliminar),
):
    """Elimina una bodega (el bodeguero solo las suyas). Responde 204 sin cuerpo."""
    services.eliminar(db, bodega_id, usuario)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
