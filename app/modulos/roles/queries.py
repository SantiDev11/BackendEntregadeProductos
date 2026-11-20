# Consultas a la base de datos del módulo Roles
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.modulos.permisos.models import Permiso
from app.modulos.roles.models import Rol
from app.modulos.usuarios.models import Usuario


def obtener(db: Session, rol_id: int) -> Rol | None:
    """Rol por id, o None si no existe."""
    return db.get(Rol, rol_id)


def existe_nombre(db: Session, nombre: str, excluir_id: int | None = None) -> bool:
    """True si ya hay un rol con ese nombre (sin distinguir mayúsculas), sin contar `excluir_id`."""
    query = db.query(Rol).filter(func.lower(Rol.nombre) == nombre.lower())
    if excluir_id is not None:
        query = query.filter(Rol.id != excluir_id)  # al editar, no compararse consigo mismo
    return query.first() is not None


def listar(db: Session, q: str | None, estado: bool | None, page: int, limit: int) -> tuple[int, list[Rol]]:
    """Devuelve (total que cumple los filtros, roles de la página con sus permisos), ordenados por id."""
    query = db.query(Rol)
    if q:
        query = query.filter(Rol.nombre.ilike(f"%{q}%"))  # contiene, sin distinguir mayúsculas
    if estado is not None:
        query = query.filter(Rol.estado == estado)  # si no viene, devuelve activos e inactivos

    total = query.count()  # total que cumple el filtro, antes de paginar
    roles = (
        query.options(selectinload(Rol.permisos))  # trae los permisos de todos los roles en una sola consulta extra
        .order_by(Rol.id)
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )
    return total, roles


def permisos_por_ids(db: Session, ids: set[int]) -> list[Permiso]:
    """Permisos cuyos ids están en la lista (los que no existan simplemente no vienen)."""
    return db.query(Permiso).filter(Permiso.id.in_(ids)).all() if ids else []


def tiene_usuarios(db: Session, rol_id: int) -> bool:
    """True si algún usuario tiene este rol."""
    return db.query(Usuario).filter(Usuario.rol_id == rol_id).first() is not None
