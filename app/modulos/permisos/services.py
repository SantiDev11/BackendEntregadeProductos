# Lógica de cada endpoint de Permisos. El router solo recibe la petición y llama a estas funciones.
from sqlalchemy.orm import Session

from app.modulos.permisos import errors, queries
from app.modulos.permisos.helpers import get_permiso_or_404, validate_unique_permiso_name
from app.modulos.permisos.models import Permiso
from app.modulos.permisos.schemas import PermisoCreate, PermisoUpdate, PermisoOut, PermisoPaginado
from app.modulos.usuarios.models import Usuario


def listar_permisos(q: str | None, estado: bool | None, page: int, limit: int, db: Session, usuario: Usuario):
    """Lista los permisos con búsqueda por nombre, filtro por estado y paginación."""
    total, permisos = queries.listar(db, q=q, estado=estado, page=page, limit=limit)

    return PermisoPaginado(
        data=[PermisoOut.model_validate(p) for p in permisos],
        total=total,
        page=page,
        limit=limit,
    )


def obtener_permiso(permiso_id: int, db: Session, usuario: Usuario):
    """Devuelve un permiso por su id."""
    return get_permiso_or_404(db, permiso_id)


def crear_permiso(datos: PermisoCreate, db: Session, usuario: Usuario):
    """Crea un permiso nuevo y registra quién lo creó."""
    validate_unique_permiso_name(db, datos.nombre)
    permiso = Permiso(**datos.model_dump(), creado_por=usuario.id, actualizado_por=usuario.id)
    db.add(permiso)
    db.commit()
    db.refresh(permiso)
    return permiso


def actualizar_permiso(datos: PermisoUpdate, permiso_id: int, db: Session, usuario: Usuario):
    """Actualiza solo los campos enviados (los que lleguen en null se ignoran)
    y registra quién hizo el cambio. Para borrar la descripción se envía "" (cadena vacía)."""
    permiso = get_permiso_or_404(db, permiso_id)
    cambios = datos.model_dump(exclude_none=True)

    if "nombre" in cambios:
        validate_unique_permiso_name(db, cambios["nombre"], excluir_id=permiso_id)

    for campo, valor in cambios.items():
        setattr(permiso, campo, valor)
    permiso.actualizado_por = usuario.id  # actualizado_en lo actualiza el mixin (onupdate)

    db.commit()
    db.refresh(permiso)
    return permiso


def eliminar_permiso(permiso_id: int, db: Session, usuario: Usuario):
    """Elimina un permiso si no está asignado a ningún rol. Responde 204 sin cuerpo."""
    permiso = get_permiso_or_404(db, permiso_id)

    # Si el permiso está asignado a algún rol, no se borra (evita el error 500 de clave foránea)
    asignado = queries.asignado_a_roles(db, permiso_id)
    if asignado:
        raise errors.asignado_a_roles()

    # Lo mismo si algún usuario lo tiene
    if queries.asignado_a_usuarios(db, permiso_id):
        raise errors.asignado_a_usuarios()

    db.delete(permiso)
    db.commit()
