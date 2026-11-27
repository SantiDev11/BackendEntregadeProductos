# Lógica de cada endpoint de Roles. El router solo recibe la petición y llama a estas funciones.
from sqlalchemy.orm import Session

from app.modulos.roles import errors, queries
from app.modulos.roles.helpers import (get_rol_or_404, validate_puede_desactivar, validate_puede_renombrar,
                                      validate_unique_rol_name)
from app.modulos.roles.models import Rol
from app.modulos.roles.schemas import RolCreate, RolEstadoUpdate, RolUpdate, RolPermisosUpdate, RolOut, RolPaginado
from app.modulos.usuarios.models import Usuario


def listar_roles(q: str | None, estado: bool | None, page: int, limit: int, db: Session, usuario: Usuario):
    """Lista los roles (con sus permisos) con búsqueda por nombre, filtro por estado y paginación."""
    total, roles = queries.listar(db, q=q, estado=estado, page=page, limit=limit)

    return RolPaginado(
        data=[RolOut.model_validate(r) for r in roles],
        total=total,
        page=page,
        limit=limit,
    )


def obtener_rol(rol_id: int, db: Session, usuario: Usuario):
    """Devuelve un rol por su id."""
    return get_rol_or_404(db, rol_id)


def crear_rol(datos: RolCreate, db: Session, usuario: Usuario):
    """Crea un rol nuevo (sin permisos) y registra quién lo creó."""
    validate_unique_rol_name(db, datos.nombre)
    rol = Rol(**datos.model_dump(), creado_por=usuario.id, actualizado_por=usuario.id)
    db.add(rol)
    db.commit()
    db.refresh(rol)
    return rol


def actualizar_rol(datos: RolUpdate, rol_id: int, db: Session, usuario: Usuario):
    """Actualiza solo los campos enviados (los que lleguen en null se ignoran)
    y registra quién hizo el cambio. Para borrar la descripción se envía "" (cadena vacía)."""
    rol = get_rol_or_404(db, rol_id)
    cambios = datos.model_dump(exclude_none=True)

    if "nombre" in cambios:
        validate_puede_renombrar(rol, cambios["nombre"], usuario)
        validate_unique_rol_name(db, cambios["nombre"], excluir_id=rol_id)
    if "estado" in cambios:
        validate_puede_desactivar(rol, cambios["estado"], usuario)
        # Cascada reversible: desactivarlo desactiva a sus usuarios; reactivarlo devuelve solo a esos
        if cambios["estado"]:
            queries.reactivar_usuarios(db, rol_id)
        else:
            queries.desactivar_usuarios(db, rol_id)

    for campo, valor in cambios.items():
        setattr(rol, campo, valor)
    rol.actualizado_por = usuario.id  # actualizado_en lo actualiza el mixin (onupdate)

    db.commit()
    db.refresh(rol)
    return rol


def cambiar_estado_rol(datos: RolEstadoUpdate, rol_id: int, db: Session, usuario: Usuario):
    """Activa o desactiva el rol, con las mismas reglas que al editarlo."""
    return actualizar_rol(RolUpdate(estado=datos.estado), rol_id, db, usuario)


def asignar_permisos_rol(datos: RolPermisosUpdate, rol_id: int, db: Session, usuario: Usuario):
    """Reemplaza todos los permisos del rol por los de la lista (vacía = sin permisos)."""
    rol = get_rol_or_404(db, rol_id)

    ids = set(datos.permisos_ids)  # ignora ids repetidos
    permisos = queries.permisos_por_ids(db, ids)

    # Si algún id no existe, no se cambia nada
    if len(permisos) != len(ids):
        raise errors.permisos_no_existen()

    rol.permisos = permisos  # reemplaza la lista completa en rol_permiso
    rol.actualizado_por = usuario.id

    db.commit()
    db.refresh(rol)
    return rol


def eliminar_rol(rol_id: int, db: Session, usuario: Usuario):
    """Elimina un rol si ningún usuario lo tiene. Responde 204 sin cuerpo."""
    rol = get_rol_or_404(db, rol_id)

    # Si algún usuario tiene este rol, no se borra (evita el error 500 de clave foránea)
    con_usuarios = queries.tiene_usuarios(db, rol_id)
    if con_usuarios:
        raise errors.tiene_usuarios()

    rol.permisos = []  # quita sus filas en rol_permiso (los permisos no se borran)
    db.delete(rol)
    db.commit()
