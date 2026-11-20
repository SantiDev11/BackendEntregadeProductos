# Endpoints de Bodegas. El usuario que no es admin solo ve y maneja las bodegas que le pertenecen.
# Las consultas a la BD están en queries.py y las validaciones en helpers.py.
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.core.deps import get_current_user, require_permiso
from app.core.docs import ERROR_401, ERROR_403, respuesta_error
from app.modulos.bodegas import queries
from app.modulos.bodegas.helpers import (MSG_BODEGUERO_INVALIDO, MSG_CODIGO_DUPLICADO, es_admin, get_bodega_or_404,
                                         validate_bodeguero, validate_unique_bodega_codigo, validate_unique_bodega_name)
from app.modulos.bodegas.models import Bodega
from app.modulos.bodegas.schemas import BodegaCreate, BodegaUpdate, BodegaOut, BodegaPaginado
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

# Mensajes de error

# Errores documentados que se repiten en este router
ERROR_404 = respuesta_error("No existe una bodega con ese id, o no le pertenece al bodeguero",
                            no_existe="Bodega no encontrada")
ERROR_400_DUPLICADO = respuesta_error(
    "Ya hay otra bodega con ese nombre o con ese código (sin distinguir mayúsculas)",
    duplicado="Ya existe una bodega con ese nombre",
    codigo_duplicado=MSG_CODIGO_DUPLICADO,
)
ERROR_400_GUARDAR = respuesta_error(
    "Nombre o código repetido, o bodeguero inválido (admin)",
    duplicado="Ya existe una bodega con ese nombre",
    codigo_duplicado=MSG_CODIGO_DUPLICADO,
    bodeguero_invalido=MSG_BODEGUERO_INVALIDO,
)
ERROR_422_ID = respuesta_error("El id de la ruta no es un número", id_invalido="bodega_id: tiene un formato inválido")


# ===== CONSULTAS (GET) =====

@router.get(
    "",
    response_model=BodegaPaginado,
    summary="Listar bodegas",
    description=f"""
Devuelve las bodegas en páginas, con búsqueda por nombre y filtros.

**Permiso requerido:** `bodegas_view`. El rol `admin` siempre tiene acceso. Requiere `Authorization: Bearer <token>`.

**Alcance:** el `admin` ve y maneja todas las bodegas; cualquier otro usuario solo las suyas (`bodeguero_id` = su id). Una bodega ajena le responde 404.

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
        422: respuesta_error(
            "Algún parámetro de la consulta no es válido",
            limit_maximo="limit: debe ser menor o igual a 100",
            page_minimo="page: debe ser mayor o igual a 1",
            estado_invalido="estado: tiene un formato inválido",
        ),
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
):
    """Lista las bodegas con búsqueda, filtros y paginación. El bodeguero solo ve las suyas."""
    if not es_admin(usuario):
        bodeguero_id = usuario.id  # el bodeguero siempre ve solo sus bodegas

    total, bodegas = queries.listar(db, q=q, estado=estado, bodeguero_id=bodeguero_id, page=page, limit=limit)

    return BodegaPaginado(
        data=[BodegaOut.model_validate(b) for b in bodegas],
        total=total,
        page=page,
        limit=limit,
    )


@router.get(
    "/{bodega_id}",
    response_model=BodegaOut,
    summary="Obtener una bodega",
    description=f"""
Devuelve una bodega por su id, con su dueño, su estado y sus datos de auditoría.

**Permiso requerido:** `bodegas_view`. El rol `admin` siempre tiene acceso. Requiere `Authorization: Bearer <token>`.

**Alcance:** el `admin` ve y maneja todas las bodegas; cualquier otro usuario solo las suyas (`bodeguero_id` = su id). Una bodega ajena le responde 404.

**Parámetros:**
- `bodega_id` (en la ruta): id de la bodega.

**Devuelve:** la bodega, o 404 si no existe (o si es de otro bodeguero).
""",
    response_description="La bodega encontrada",
    responses={401: ERROR_401, 403: ERROR_403, 404: ERROR_404, 422: ERROR_422_ID},
)
def obtener_bodega(
    bodega_id: int = Path(description="Id de la bodega.", examples=[1]),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(puede_ver),
):
    """Devuelve una bodega por su id (el bodeguero solo las suyas)."""
    return get_bodega_or_404(db, bodega_id, usuario)


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
- `nombre`: de 1 a 100 caracteres.
- `codigo`: código interno, hasta 30 caracteres.
- `direccion`: hasta 200 caracteres.
- `ciudad` y `departamento`: hasta 100 caracteres.
- `telefono`: hasta 30 caracteres. `correo`: formato de correo válido, hasta 100.
- Datos de quién recibe: `recibe_nombre` (100), `recibe_documento` (30), `recibe_cargo` (100) y `recibe_telefono` (30).
- `bodeguero_id` (opcional, **solo admin**): dueño de la bodega.
- `estado` (opcional): por defecto `true` (activa).

**Reglas:**
- **Dueño:** si la crea un bodeguero, el dueño es él mismo y `bodeguero_id` se ignora.
  Si la crea el admin, puede indicar `bodeguero_id` (un usuario con rol bodeguero) o dejarla sin dueño.
- El nombre debe ser único **sin distinguir mayúsculas**: si ya existe "Bodega Central", "bodega central" da 400.
- El `codigo` se guarda en **mayúsculas** y también debe ser único: "bod-01" choca con "BOD-01".
- Se quitan los espacios al inicio y al final. Un campo que falte, o que llegue vacío (`""` o solo espacios), da 422.
- `creado_por`, `actualizado_por`, `creado_en` y `actualizado_en` los pone el servidor.
  Si se envían en el cuerpo, se ignoran.

**Devuelve:** 201 con la bodega creada.
""",
    response_description="La bodega creada, con su id, su dueño y datos de auditoría",
    responses={
        400: ERROR_400_GUARDAR,
        401: ERROR_401,
        403: ERROR_403,
        422: respuesta_error(
            "El cuerpo no cumple las validaciones",
            faltantes="codigo: es obligatorio; direccion: es obligatorio; ciudad: es obligatorio; ...",
            nombre_vacio="nombre: no puede estar vacío",
            nombre_largo="nombre: es demasiado largo",
            codigo_largo="codigo: es demasiado largo",
            correo_invalido="correo: formato de correo inválido",
            json_invalido="El cuerpo de la petición no es un JSON válido",
        ),
    },
)
def crear_bodega(
    datos: BodegaCreate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(puede_crear),
):
    """Crea una bodega nueva, define su dueño y registra quién la creó."""
    validate_unique_bodega_name(db, datos.nombre)

    valores = datos.model_dump()
    valores["codigo"] = valores["codigo"].upper()  # el código siempre se guarda en mayúsculas
    validate_unique_bodega_codigo(db, valores["codigo"])

    if es_admin(usuario):
        if valores.get("bodeguero_id") is not None:
            validate_bodeguero(db, valores["bodeguero_id"])
    else:
        valores["bodeguero_id"] = usuario.id  # el bodeguero siempre queda como dueño de lo que crea

    bodega = Bodega(**valores, creado_por=usuario.id, actualizado_por=usuario.id)
    db.add(bodega)
    db.commit()
    db.refresh(bodega)
    return bodega


# ===== EDITAR (PUT) =====

@router.put(
    "/{bodega_id}",
    response_model=BodegaOut,
    summary="Editar una bodega",
    description=f"""
Actualiza una bodega existente. **Solo cambia los campos que se envían.**

**Permiso requerido:** `bodegas_edit`. El rol `admin` siempre tiene acceso. Requiere `Authorization: Bearer <token>`.

**Alcance:** el `admin` ve y maneja todas las bodegas; cualquier otro usuario solo las suyas (`bodeguero_id` = su id). Una bodega ajena le responde 404.

**Parámetros:**
- `bodega_id` (en la ruta): id de la bodega a editar.

**Cuerpo (se envían solo los que cambian):**
- `nombre`: nuevo nombre, de 1 a 100 caracteres.
- `codigo`, `direccion`, `ciudad`, `departamento`, `telefono`, `correo`: datos de la bodega.
- `recibe_nombre`, `recibe_documento`, `recibe_cargo`, `recibe_telefono`: datos de quién recibe.
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
        400: ERROR_400_GUARDAR,
        401: ERROR_401,
        403: ERROR_403,
        404: ERROR_404,
        422: respuesta_error(
            "El id o el cuerpo no cumplen las validaciones",
            id_invalido="bodega_id: tiene un formato inválido",
            nombre_vacio="nombre: no puede estar vacío",
            nombre_largo="nombre: es demasiado largo",
            direccion_larga="direccion: es demasiado largo",
            correo_invalido="correo: formato de correo inválido",
            estado_invalido="estado: tiene un formato inválido",
        ),
    },
)
def actualizar_bodega(
    datos: BodegaUpdate,
    bodega_id: int = Path(description="Id de la bodega a editar.", examples=[1]),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(puede_editar),
):
    """Actualiza solo los campos enviados (los que lleguen en null se ignoran)
    y registra quién hizo el cambio. Ningún dato puede quedar vacío (lo valida el schema)."""
    bodega = get_bodega_or_404(db, bodega_id, usuario)
    cambios = datos.model_dump(exclude_none=True)  # null = no se cambia

    # Solo el admin puede cambiar el dueño; si lo envía un bodeguero, se ignora
    if not es_admin(usuario):
        cambios.pop("bodeguero_id", None)
    elif "bodeguero_id" in cambios:
        validate_bodeguero(db, cambios["bodeguero_id"])

    if "nombre" in cambios:
        validate_unique_bodega_name(db, cambios["nombre"], excluir_id=bodega_id)

    if cambios.get("codigo"):
        cambios["codigo"] = cambios["codigo"].upper()  # el código siempre se guarda en mayúsculas
        validate_unique_bodega_codigo(db, cambios["codigo"], excluir_id=bodega_id)

    for campo, valor in cambios.items():
        setattr(bodega, campo, valor)
    bodega.actualizado_por = usuario.id  # actualizado_en lo actualiza el mixin (onupdate)

    db.commit()
    db.refresh(bodega)
    return bodega


# ===== ELIMINAR (DELETE) =====

@router.delete(
    "/{bodega_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar una bodega",
    description=f"""
Elimina una bodega de forma **definitiva** (no es un borrado lógico).

**Permiso requerido:** `bodegas_delete`. El rol `admin` siempre tiene acceso. Requiere `Authorization: Bearer <token>`.

**Alcance:** el `admin` ve y maneja todas las bodegas; cualquier otro usuario solo las suyas (`bodeguero_id` = su id). Una bodega ajena le responde 404.

**Parámetros:**
- `bodega_id` (en la ruta): id de la bodega a eliminar.

**Reglas:**
- Si la bodega tiene facturas, no se elimina y responde 400.
- Para desactivar una bodega sin borrarla, usa `PUT` con `{{"estado": false}}`.

**Devuelve:** 204 **sin cuerpo**.
""",
    response_description="Bodega eliminada. La respuesta no tiene cuerpo",
    responses={
        400: respuesta_error("La bodega tiene facturas o tipos",
                             en_uso="No se puede eliminar: la bodega tiene facturas",
                             con_tipos="No se puede eliminar: la bodega tiene tipos"),
        401: ERROR_401, 403: ERROR_403, 404: ERROR_404, 422: ERROR_422_ID,
    },
)
def eliminar_bodega(
    bodega_id: int = Path(description="Id de la bodega a eliminar.", examples=[1]),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(puede_eliminar),
):
    """Elimina una bodega (el bodeguero solo las suyas). Responde 204 sin cuerpo."""
    bodega = get_bodega_or_404(db, bodega_id, usuario)

    # Si la bodega tiene facturas, no se borra (evita el error 500 de clave foránea)
    if queries.tiene_facturas(db, bodega_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="No se puede eliminar: la bodega tiene facturas")
    # Tampoco si tiene tipos en su catálogo (primero hay que borrarlos o moverlos)
    if queries.tiene_tipos(db, bodega_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="No se puede eliminar: la bodega tiene tipos")

    db.delete(bodega)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
