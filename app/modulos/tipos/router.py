# Endpoints de Tipos. Cada tipo pertenece a una bodega (catálogo por bodega).
# Las consultas a la BD están en queries.py y las validaciones en helpers.py.
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.core.deps import get_current_user, require_permiso
from app.core.docs import ERROR_401, respuesta_error
from app.modulos.tipos import queries
from app.modulos.tipos.helpers import (MSG_BODEGA_INVALIDA, MSG_SIN_BODEGA, MSG_TIPO_AJENO, MSG_VARIAS_BODEGAS,
                                       bodega_para_nuevo_tipo, bodegas_permitidas, es_admin, get_tipo_or_404,
                                       validate_bodega_existe, validate_unique_tipo_name)
from app.modulos.tipos.models import Tipo
from app.modulos.tipos.schemas import TipoCreate, TipoUpdate, TipoOut, TipoPaginado
from app.modulos.usuarios.models import Usuario

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

# Errores documentados que se repiten en este router
ERROR_404 = respuesta_error("No existe un tipo con ese id", no_existe="Tipo no encontrado")
ERROR_403_TIPO = respuesta_error(
    "Sin el permiso, o el tipo es de una bodega que no es del usuario",
    sin_permiso="No tiene permiso para esta acción",
    tipo_ajeno=MSG_TIPO_AJENO,
)
ERROR_422_ID = respuesta_error("El id de la ruta no es un número", id_invalido="tipo_id: tiene un formato inválido")


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
        403: respuesta_error("Sin el permiso", sin_permiso="No tiene permiso para esta acción"),
        422: respuesta_error(
            "Algún parámetro de la consulta no es válido",
            limit_maximo="limit: debe ser menor o igual a 100",
            page_minimo="page: debe ser mayor o igual a 1",
            estado_invalido="estado: tiene un formato inválido",
            bodega_invalida="bodega_id: tiene un formato inválido",
        ),
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
    total, tipos = queries.listar(db, q=q, estado=estado, bodega_id=bodega_id,
                                  bodegas_permitidas=bodegas_permitidas(db, usuario), page=page, limit=limit)

    return TipoPaginado(
        data=[TipoOut.model_validate(t) for t in tipos],
        total=total,
        page=page,
        limit=limit,
    )


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
    responses={401: ERROR_401, 403: ERROR_403_TIPO, 404: ERROR_404, 422: ERROR_422_ID},
)
def obtener_tipo(
    tipo_id: int = Path(description="Id del tipo.", examples=[1]),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(puede_ver),
):
    """Devuelve un tipo por su id (si es de una de las bodegas del usuario, o si es admin)."""
    return get_tipo_or_404(db, tipo_id, usuario)


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
        400: respuesta_error(
            "Nombre repetido en la bodega, o problema con la bodega",
            duplicado="Ya existe un tipo con ese nombre en esta bodega",
            sin_bodega=MSG_SIN_BODEGA,
            varias_bodegas=MSG_VARIAS_BODEGAS,
            bodega_invalida=MSG_BODEGA_INVALIDA,
        ),
        401: ERROR_401,
        403: respuesta_error("Sin el permiso", sin_permiso="No tiene permiso para esta acción"),
        422: respuesta_error(
            "El cuerpo no cumple las validaciones",
            nombre_faltante="nombre: es obligatorio",
            nombre_vacio="nombre: no puede estar vacío",
            nombre_largo="nombre: es demasiado largo",
            json_invalido="El cuerpo de la petición no es un JSON válido",
        ),
    },
)
def crear_tipo(
    datos: TipoCreate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(puede_crear),
):
    """Crea un tipo en la bodega que corresponde y registra quién lo creó."""
    bodega_id = bodega_para_nuevo_tipo(db, usuario, datos.bodega_id)
    validate_unique_tipo_name(db, datos.nombre, bodega_id)

    valores = datos.model_dump()
    valores["bodega_id"] = bodega_id
    tipo = Tipo(**valores, creado_por=usuario.id, actualizado_por=usuario.id)
    db.add(tipo)
    db.commit()
    db.refresh(tipo)
    return tipo


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
        400: respuesta_error(
            "Nombre repetido en la bodega, o bodega inválida (admin)",
            duplicado="Ya existe un tipo con ese nombre en esta bodega",
            bodega_invalida=MSG_BODEGA_INVALIDA,
        ),
        401: ERROR_401,
        403: ERROR_403_TIPO,
        404: ERROR_404,
        422: respuesta_error(
            "El id o el cuerpo no cumplen las validaciones",
            id_invalido="tipo_id: tiene un formato inválido",
            nombre_vacio="nombre: no puede estar vacío",
            nombre_largo="nombre: es demasiado largo",
            estado_invalido="estado: tiene un formato inválido",
        ),
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
    tipo = get_tipo_or_404(db, tipo_id, usuario)
    cambios = datos.model_dump(exclude_none=True)

    # Solo el admin puede mover el tipo a otra bodega; si lo envía otro usuario, se ignora
    if not es_admin(usuario):
        cambios.pop("bodega_id", None)
    elif "bodega_id" in cambios:
        validate_bodega_existe(db, cambios["bodega_id"])

    # El nombre se valida contra la bodega en la que va a quedar el tipo
    if "nombre" in cambios or "bodega_id" in cambios:
        validate_unique_tipo_name(db, cambios.get("nombre", tipo.nombre),
                                  cambios.get("bodega_id", tipo.bodega_id), excluir_id=tipo_id)

    for campo, valor in cambios.items():
        setattr(tipo, campo, valor)
    tipo.actualizado_por = usuario.id  # actualizado_en lo actualiza el mixin (onupdate)

    db.commit()
    db.refresh(tipo)
    return tipo


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
        400: respuesta_error("El tipo está usado en facturas", en_uso="No se puede eliminar: el tipo está usado en facturas"),
        401: ERROR_401, 403: ERROR_403_TIPO, 404: ERROR_404, 422: ERROR_422_ID,
    },
)
def eliminar_tipo(
    tipo_id: int = Path(description="Id del tipo a eliminar.", examples=[1]),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(puede_eliminar),
):
    """Elimina un tipo (si es de una de las bodegas del usuario, o si es admin). Responde 204 sin cuerpo."""
    tipo = get_tipo_or_404(db, tipo_id, usuario)

    # Si el tipo está usado en alguna línea de factura, no se borra (evita el error 500 de clave foránea)
    if queries.usado_en_facturas(db, tipo_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="No se puede eliminar: el tipo está usado en facturas")

    db.delete(tipo)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
