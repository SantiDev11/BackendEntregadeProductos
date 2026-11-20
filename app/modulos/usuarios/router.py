# Endpoints de Usuarios y de sus permisos. La contraseña nunca se devuelve.
# Las consultas a la BD están en queries.py y las validaciones en helpers.py.
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.core.deps import get_current_user, require_permiso
from app.core.docs import ERROR_401, ERROR_403, respuesta_error
from app.core.security import hash_password
from app.modulos.roles.schemas import PermisoResumen
from app.modulos.usuarios import queries
from app.modulos.usuarios.helpers import (MSG_CORREO_DUPLICADO, MSG_DOCUMENTO_DUPLICADO, MSG_ROL_NO_EXISTE,
                                          get_permiso_or_404, get_usuario_or_404, vacios_a_none, validate_rol_exists,
                                          validate_unique_usuario_documento, validate_unique_usuario_email)
from app.modulos.usuarios.models import Usuario
from app.modulos.usuarios.schemas import (UsuarioCreate, UsuarioUpdate, UsuarioOut, UsuarioPaginado, UsuarioPermisosOut,
                                          UsuarioPermisosUpdate)

# Permiso que exige cada acción (los permisos se leen de la BD en cada petición; el rol admin siempre pasa)
puede_ver = require_permiso("usuarios_view")
puede_crear = require_permiso("usuarios_create")
puede_editar = require_permiso("usuarios_edit")
puede_eliminar = require_permiso("usuarios_delete")

# Todos los endpoints exigen sesión; cada uno exige además su permiso (ver arriba)
router = APIRouter(
    prefix="/usuarios",
    tags=["Usuarios"],
    dependencies=[Depends(get_current_user)],
)

# Errores documentados que se repiten en este router
ERROR_404 = respuesta_error("No existe un usuario con ese id", no_existe="Usuario no encontrado")
ERROR_422_ID = respuesta_error("El id de la ruta no es un número", id_invalido="usuario_id: tiene un formato inválido")


# ===== CONSULTAS (GET) =====

@router.get(
    "",
    response_model=UsuarioPaginado,
    summary="Listar usuarios",
    description="""
Devuelve los usuarios en páginas, con búsqueda por nombre o correo y filtros por estado y rol.

**Permiso requerido:** `usuarios_view`. El rol `admin` siempre tiene acceso. Requiere `Authorization: Bearer <token>`.

**Parámetros (todos opcionales):**
- `q`: busca usuarios cuyo **nombre o correo** contenga el texto, sin distinguir mayúsculas
  (`entrega` encuentra "admin@entrega.com").
- `estado`: `true` solo activos, `false` solo inactivos. Si no se envía, devuelve todos.
- `rol`: solo los usuarios de ese rol, por **nombre** (por ejemplo `?rol=cliente`).
- `rol_id`: solo los usuarios de ese rol, por **id**.
- `page`: número de página, empieza en 1.
- `limit`: elementos por página, por defecto 10 y máximo 100.

**Reglas:**
- Los resultados se ordenan por `id`.
- `total` es la cantidad que cumple los filtros, no solo la de la página actual.
- Cada usuario trae `rol_id` y `rol` (el nombre del rol como texto). **Nunca** trae la contraseña.

**Devuelve:** `{"data": [...], "total": n, "page": p, "limit": l}`.
""",
    response_description="Página de usuarios (sin contraseñas) con el total que cumple los filtros",
    responses={
        401: ERROR_401,
        403: ERROR_403,
        422: respuesta_error(
            "Algún parámetro de la consulta no es válido",
            limit_maximo="limit: debe ser menor o igual a 100",
            page_minimo="page: debe ser mayor o igual a 1",
            estado_invalido="estado: tiene un formato inválido",
            rol_id_invalido="rol_id: tiene un formato inválido",
        ),
    },
)
def listar_usuarios(
    q: str | None = Query(None, description="Texto a buscar en el nombre o el correo (contiene, sin distinguir mayúsculas)."),
    estado: bool | None = Query(None, description="Filtra por estado: `true` activos, `false` inactivos. Si no se envía, devuelve todos."),
    rol: str | None = Query(None, description="Filtra por nombre de rol, por ejemplo `cliente`. Si no se envía, devuelve todos."),
    rol_id: int | None = Query(None, description="Filtra por rol: solo los usuarios con ese `rol_id`. Si no se envía, devuelve todos."),
    page: int = Query(1, ge=1, description="Número de página. Empieza en 1."),
    limit: int = Query(10, ge=1, le=100, description="Elementos por página. Por defecto 10, máximo 100."),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(puede_ver),
):
    """Lista los usuarios con búsqueda por nombre o correo, filtros por estado y rol, y paginación."""
    total, usuarios = queries.listar(db, q=q, estado=estado, rol=rol, rol_id=rol_id, page=page, limit=limit)

    return UsuarioPaginado(
        data=[UsuarioOut.model_validate(u) for u in usuarios],
        total=total,
        page=page,
        limit=limit,
    )


@router.get(
    "/{usuario_id}",
    response_model=UsuarioOut,
    summary="Obtener un usuario",
    description="""
Devuelve un usuario por su id, con su rol, su estado y sus datos de auditoría.

**Permiso requerido:** `usuarios_view`. El rol `admin` siempre tiene acceso. Requiere `Authorization: Bearer <token>`.

**Parámetros:**
- `usuario_id` (en la ruta): id del usuario.

**Devuelve:** el usuario (sin contraseña), o 404 si no existe.
""",
    response_description="El usuario encontrado (sin contraseña)",
    responses={401: ERROR_401, 403: ERROR_403, 404: ERROR_404, 422: ERROR_422_ID},
)
def obtener_usuario(
    usuario_id: int = Path(description="Id del usuario.", examples=[1]),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(puede_ver),
):
    """Devuelve un usuario por su id."""
    return get_usuario_or_404(db, usuario_id)


# ===== CREAR (POST) =====

@router.post(
    "",
    response_model=UsuarioOut,
    status_code=status.HTTP_201_CREATED,
    summary="Crear un usuario",
    description="""
Crea un usuario nuevo con su contraseña y su rol.

**Permiso requerido:** `usuarios_create`. El rol `admin` siempre tiene acceso. Requiere `Authorization: Bearer <token>`.

**Cuerpo:**
- `nombre` (**obligatorio**): de 1 a 100 caracteres. Se quitan los espacios al inicio y al final.
- `correo` (**obligatorio**): formato de correo válido.
- `contrasena` (**obligatorio**): de 8 a 72 caracteres.
- `rol_id` (**obligatorio**): id de un rol existente (ver `GET /roles`).
- Datos para facturar (opcionales): `tipo_documento` (`CC`, `NIT`, `CE` o `PA`), `numero_documento`,
  `telefono`, `direccion` y `ciudad`.
- `estado` (opcional): por defecto `true` (activo).

**Reglas:**
- El correo se guarda en **minúsculas** y debe ser único **sin distinguir mayúsculas**:
  si ya existe "cliente@entrega.com", "CLIENTE@ENTREGA.COM" da 400.
- Si el `rol_id` no existe, responde 400.
- **Permisos:** el rol funciona como **plantilla**. Al crear el usuario se le copian los permisos que tenga su rol
  en ese momento. Después se cambian con `PUT /usuarios/{id}/permisos`.
- El `numero_documento` debe ser único. `tipo_documento` se acepta en minúsculas y se guarda en mayúsculas.
- Los campos opcionales que no se envían, o que llegan como `""`, quedan en `null`.
- La contraseña se guarda cifrada con bcrypt y **nunca** se devuelve.
- `creado_por`, `actualizado_por`, `creado_en` y `actualizado_en` los pone el servidor.
  Si se envían en el cuerpo, se ignoran.

**Devuelve:** 201 con el usuario creado, con `rol` como texto y sin contraseña.
""",
    response_description="El usuario creado (sin contraseña), con su id, rol y datos de auditoría",
    responses={
        400: respuesta_error(
            "El correo o el documento ya están registrados, o el rol no existe",
            correo_duplicado=MSG_CORREO_DUPLICADO,
            documento_duplicado=MSG_DOCUMENTO_DUPLICADO,
            rol_inexistente=MSG_ROL_NO_EXISTE,
        ),
        401: ERROR_401,
        403: ERROR_403,
        422: respuesta_error(
            "El cuerpo no cumple las validaciones",
            campos_faltantes="nombre: es obligatorio; correo: es obligatorio; contrasena: es obligatorio; rol_id: es obligatorio",
            correo_invalido="correo: formato de correo inválido",
            contrasena_corta="contrasena: es demasiado corto",
            contrasena_larga="contrasena: es demasiado largo",
            rol_id_invalido="rol_id: tiene un formato inválido",
            tipo_documento_invalido="tipo_documento: debe ser CC, NIT, CE o PA",
        ),
    },
)
def crear_usuario(
    datos: UsuarioCreate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(puede_crear),
):
    """Crea un usuario nuevo (correo en minúsculas, contraseña cifrada) y registra quién lo creó."""
    validate_unique_usuario_email(db, datos.correo)
    rol = validate_rol_exists(db, datos.rol_id)

    valores = vacios_a_none(datos.model_dump())  # "" se guarda como NULL
    if valores.get("numero_documento"):
        validate_unique_usuario_documento(db, valores["numero_documento"])

    valores["correo"] = valores["correo"].lower()  # el correo siempre se guarda en minúsculas
    valores["contrasena"] = hash_password(valores["contrasena"])  # nunca se guarda en texto plano

    nuevo = Usuario(**valores, creado_por=usuario.id, actualizado_por=usuario.id)
    nuevo.permisos = list(rol.permisos)  # el rol es la plantilla: se copian sus permisos actuales
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo


# ===== EDITAR (PUT) =====

@router.put(
    "/{usuario_id}",
    response_model=UsuarioOut,
    summary="Editar un usuario",
    description="""
Actualiza un usuario existente. **Solo cambia los campos que se envían.**

**Permiso requerido:** `usuarios_edit`. El rol `admin` siempre tiene acceso. Requiere `Authorization: Bearer <token>`.

**Parámetros:**
- `usuario_id` (en la ruta): id del usuario a editar.

**Cuerpo (todos opcionales):**
- `nombre`: nuevo nombre, de 1 a 100 caracteres.
- `correo`: nuevo correo (se guarda en minúsculas).
- `contrasena`: nueva contraseña, de 8 a 72 caracteres.
- `rol_id`: id de un rol existente.
- `tipo_documento`, `numero_documento`, `telefono`, `direccion`, `ciudad`: datos para facturar.
- `estado`: `true` para activar, `false` para desactivar. Un usuario inactivo no puede iniciar sesión
  y su token deja de funcionar.

**Reglas:**
- Un campo que no se envía, o que llega en `null`, no se cambia.
- Para **borrar** un dato para facturar se envía `""` (cadena vacía): queda en `null`.
- El `numero_documento` no puede tenerlo **otro** usuario.
- **Contraseña:** si no se envía, la actual **no** se toca. Si se envía, se guarda cifrada la nueva.
- El correo no puede tenerlo **otro** usuario (sin distinguir mayúsculas). Volver a enviar el mismo correo del usuario no es error.
- Si el `rol_id` no existe, responde 400.
- Cambiar el `rol_id` **no cambia los permisos** del usuario. Esos se manejan con `PUT /usuarios/{id}/permisos`.
- El admin **no puede desactivarse a sí mismo** (`estado: false` sobre su propio id).
- El servidor guarda en `actualizado_por` el id del usuario que hace el cambio y actualiza `actualizado_en`.
  `creado_por` y `creado_en` no cambian.

**Devuelve:** el usuario actualizado, sin contraseña.
""",
    response_description="El usuario con los cambios aplicados (sin contraseña)",
    responses={
        400: respuesta_error(
            "Correo o documento repetido, rol inexistente o intento de desactivarse a sí mismo",
            correo_duplicado=MSG_CORREO_DUPLICADO,
            documento_duplicado=MSG_DOCUMENTO_DUPLICADO,
            rol_inexistente=MSG_ROL_NO_EXISTE,
            desactivarse="No puede desactivar su propio usuario",
        ),
        401: ERROR_401,
        403: ERROR_403,
        404: ERROR_404,
        422: respuesta_error(
            "El id o el cuerpo no cumplen las validaciones",
            id_invalido="usuario_id: tiene un formato inválido",
            correo_invalido="correo: formato de correo inválido",
            contrasena_corta="contrasena: es demasiado corto",
            rol_id_invalido="rol_id: tiene un formato inválido",
            tipo_documento_invalido="tipo_documento: debe ser CC, NIT, CE o PA",
            estado_invalido="estado: tiene un formato inválido",
        ),
    },
)
def actualizar_usuario(
    datos: UsuarioUpdate,
    usuario_id: int = Path(description="Id del usuario a editar.", examples=[3]),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(puede_editar),
):
    """Actualiza solo los campos enviados (los que lleguen en null se ignoran)
    y registra quién hizo el cambio. Si no llega contraseña, el hash no se toca."""
    editado = get_usuario_or_404(db, usuario_id)
    # null se ignora (exclude_none); "" sí llega y se convierte en None para borrar el campo
    cambios = vacios_a_none(datos.model_dump(exclude_none=True))

    # El admin no puede desactivarse a sí mismo (se quedaría sin acceso)
    if usuario_id == usuario.id and cambios.get("estado") is False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puede desactivar su propio usuario",
        )

    if "correo" in cambios:
        cambios["correo"] = cambios["correo"].lower()  # el correo siempre se guarda en minúsculas
        validate_unique_usuario_email(db, cambios["correo"], excluir_id=usuario_id)

    if "rol_id" in cambios:
        validate_rol_exists(db, cambios["rol_id"])

    if cambios.get("numero_documento"):
        validate_unique_usuario_documento(db, cambios["numero_documento"], excluir_id=usuario_id)

    if "contrasena" in cambios:
        cambios["contrasena"] = hash_password(cambios["contrasena"])  # se guarda el nuevo hash

    for campo, valor in cambios.items():
        setattr(editado, campo, valor)
    editado.actualizado_por = usuario.id  # actualizado_en lo actualiza el mixin (onupdate)

    db.commit()
    db.refresh(editado)
    return editado


# ===== PERMISOS DEL USUARIO =====
# Los permisos efectivos de cada usuario son SOLO los suyos (tabla usuario_permisos).
# El rol únicamente sirve de plantilla al crear el usuario.

ERROR_404_USUARIO_O_PERMISO = respuesta_error(
    "No existe el usuario o el permiso",
    usuario="Usuario no encontrado",
    permiso="Permiso no encontrado",
)
ERROR_422_IDS = respuesta_error(
    "Algún id de la ruta no es un número",
    usuario_id="usuario_id: tiene un formato inválido",
    permiso_id="permiso_id: tiene un formato inválido",
)


@router.get(
    "/{usuario_id}/permisos",
    response_model=UsuarioPermisosOut,
    summary="Ver los permisos de un usuario",
    description="""
Devuelve los permisos **efectivos** del usuario.

**Permiso requerido:** `usuarios_view`. El rol `admin` siempre tiene acceso. Requiere `Authorization: Bearer <token>`.

**Devuelve:** `{"data": [{"id": 1, "nombre": "ver_facturas"}, ...]}`, ordenados por id (lista vacía si no tiene).
""",
    response_description="Permisos del usuario",
    responses={401: ERROR_401, 403: ERROR_403, 404: ERROR_404, 422: ERROR_422_ID},
)
def ver_permisos_usuario(
    usuario_id: int = Path(description="Id del usuario.", examples=[3]),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(puede_ver),
):
    """Permisos efectivos del usuario."""
    usuario = get_usuario_or_404(db, usuario_id)
    return UsuarioPermisosOut(data=[PermisoResumen.model_validate(p) for p in usuario.permisos])


@router.put(
    "/{usuario_id}/permisos",
    response_model=UsuarioOut,
    summary="Asignar permisos a un usuario",
    description="""
**Reemplaza** todos los permisos del usuario por la lista enviada. Solo afecta a ese usuario, no a su rol ni a otros usuarios.

**Permiso requerido:** `usuarios_edit`. El rol `admin` siempre tiene acceso. Requiere `Authorization: Bearer <token>`.

**Cuerpo:** `{"permisos_ids": [1, 2]}`.

**Reglas:**
- El usuario queda **exactamente** con los permisos de la lista. Los que no estén se le quitan.
- `[]` le quita todos los permisos.
- Los ids repetidos se ignoran.
- Si **algún** id no existe, responde 400 y **no cambia nada**.
- Si el usuario no existe, responde 404.
- El servidor guarda en `actualizado_por` el id del admin que hace el cambio.

**Devuelve:** el usuario con su nueva lista de `permisos`.
""",
    response_description="El usuario con sus permisos actualizados",
    responses={
        400: respuesta_error("Algún id no corresponde a un permiso existente", permiso_inexistente="Uno o más permisos no existen"),
        401: ERROR_401,
        403: ERROR_403,
        404: ERROR_404,
        422: respuesta_error(
            "El id o el cuerpo no cumplen las validaciones",
            id_invalido="usuario_id: tiene un formato inválido",
            lista_faltante="permisos_ids: es obligatorio",
            no_es_lista="permisos_ids: tiene un formato inválido",
        ),
    },
)
def asignar_permisos_usuario(
    datos: UsuarioPermisosUpdate,
    usuario_id: int = Path(description="Id del usuario.", examples=[3]),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(puede_editar),
):
    """Reemplaza todos los permisos del usuario por los de la lista (vacía = sin permisos)."""
    editado = get_usuario_or_404(db, usuario_id)

    ids = set(datos.permisos_ids)  # ignora ids repetidos
    permisos = queries.permisos_por_ids(db, ids)

    # Si algún id no existe, no se cambia nada
    if len(permisos) != len(ids):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uno o más permisos no existen")

    editado.permisos = permisos  # reemplaza la lista completa en usuario_permisos
    editado.actualizado_por = usuario.id
    db.commit()
    db.refresh(editado)
    return editado


@router.post(
    "/{usuario_id}/permisos/{permiso_id}",
    response_model=UsuarioOut,
    summary="Agregar un permiso a un usuario",
    description="""
Agrega **un** permiso al usuario sin tocar los demás. Si ya lo tenía, no pasa nada (responde 200 igual).

**Permiso requerido:** `usuarios_edit`. El rol `admin` siempre tiene acceso. Requiere `Authorization: Bearer <token>`.

**Devuelve:** el usuario con su lista de `permisos`. Si el usuario o el permiso no existen, responde 404.
""",
    response_description="El usuario con el permiso agregado",
    responses={401: ERROR_401, 403: ERROR_403, 404: ERROR_404_USUARIO_O_PERMISO, 422: ERROR_422_IDS},
)
def agregar_permiso_usuario(
    usuario_id: int = Path(description="Id del usuario.", examples=[3]),
    permiso_id: int = Path(description="Id del permiso a agregar.", examples=[1]),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(puede_editar),
):
    """Agrega un permiso al usuario (idempotente)."""
    editado = get_usuario_or_404(db, usuario_id)
    permiso = get_permiso_or_404(db, permiso_id)
    if permiso not in editado.permisos:
        editado.permisos.append(permiso)
        editado.actualizado_por = usuario.id
        db.commit()
        db.refresh(editado)
    return editado


@router.delete(
    "/{usuario_id}/permisos/{permiso_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Quitar un permiso a un usuario",
    description="""
Quita **un** permiso al usuario sin tocar los demás. Si no lo tenía, no pasa nada (responde 204 igual).
El permiso en sí **no** se borra.

**Permiso requerido:** `usuarios_edit`. El rol `admin` siempre tiene acceso. Requiere `Authorization: Bearer <token>`.

**Devuelve:** 204 **sin cuerpo**. Si el usuario o el permiso no existen, responde 404.
""",
    response_description="Permiso quitado. La respuesta no tiene cuerpo",
    responses={401: ERROR_401, 403: ERROR_403, 404: ERROR_404_USUARIO_O_PERMISO, 422: ERROR_422_IDS},
)
def quitar_permiso_usuario(
    usuario_id: int = Path(description="Id del usuario.", examples=[3]),
    permiso_id: int = Path(description="Id del permiso a quitar.", examples=[1]),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(puede_editar),
):
    """Quita un permiso al usuario (idempotente). Responde 204 sin cuerpo."""
    editado = get_usuario_or_404(db, usuario_id)
    permiso = get_permiso_or_404(db, permiso_id)
    if permiso in editado.permisos:
        editado.permisos.remove(permiso)
        editado.actualizado_por = usuario.id
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ===== ELIMINAR (DELETE) =====

@router.delete(
    "/{usuario_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar un usuario",
    description="""
Elimina un usuario de forma **definitiva** (no es un borrado lógico).

**Permiso requerido:** `usuarios_delete`. El rol `admin` siempre tiene acceso. Requiere `Authorization: Bearer <token>`.

**Parámetros:**
- `usuario_id` (en la ruta): id del usuario a eliminar.

**Reglas:**
- El admin **no puede eliminarse a sí mismo**.
- Para quitarle el acceso sin borrarlo, usa `PUT` con `{"estado": false}`.

**Devuelve:** 204 **sin cuerpo**.
""",
    response_description="Usuario eliminado. La respuesta no tiene cuerpo",
    responses={
        400: respuesta_error(
            "Intento de eliminar el propio usuario",
            eliminarse="No puede eliminar su propio usuario",
            con_facturas="No se puede eliminar: el usuario tiene facturas asociadas",
        ),
        401: ERROR_401,
        403: ERROR_403,
        404: ERROR_404,
        422: ERROR_422_ID,
    },
)
def eliminar_usuario(
    usuario_id: int = Path(description="Id del usuario a eliminar.", examples=[3]),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(puede_eliminar),
):
    """Elimina un usuario (no el propio). Responde 204 sin cuerpo."""
    eliminado = get_usuario_or_404(db, usuario_id)

    # El admin no puede borrarse a sí mismo
    if usuario_id == usuario.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puede eliminar su propio usuario",
        )

    # Si el usuario tiene facturas (como cliente o como emisor), no se borra (evita el error 500)
    if queries.tiene_facturas(db, usuario_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="No se puede eliminar: el usuario tiene facturas asociadas")

    db.delete(eliminado)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
