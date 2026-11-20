# Consultas a la base de datos del módulo Permisos
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.modulos.permisos.models import Permiso
from app.modulos.roles.models import rol_permiso
from app.modulos.usuarios.models import usuario_permisos


def obtener(db: Session, permiso_id: int) -> Permiso | None:
    """Permiso por id, o None si no existe."""
    return db.get(Permiso, permiso_id)


def existe_nombre(db: Session, nombre: str, excluir_id: int | None = None) -> bool:
    """True si ya hay un permiso con ese nombre (sin distinguir mayúsculas), sin contar `excluir_id`."""
    query = db.query(Permiso).filter(func.lower(Permiso.nombre) == nombre.lower())
    if excluir_id is not None:
        query = query.filter(Permiso.id != excluir_id)  # al editar, no compararse consigo mismo
    return query.first() is not None


def listar(db: Session, q: str | None, estado: bool | None, page: int, limit: int) -> tuple[int, list[Permiso]]:
    """Devuelve (total que cumple los filtros, permisos de la página), ordenados por id."""
    query = db.query(Permiso)
    if q:
        query = query.filter(Permiso.nombre.ilike(f"%{q}%"))  # contiene, sin distinguir mayúsculas
    if estado is not None:
        query = query.filter(Permiso.estado == estado)  # si no viene, devuelve activos e inactivos

    total = query.count()  # total que cumple el filtro, antes de paginar
    permisos = query.order_by(Permiso.id).offset((page - 1) * limit).limit(limit).all()
    return total, permisos


def asignado_a_roles(db: Session, permiso_id: int) -> bool:
    """True si el permiso está en la plantilla de algún rol."""
    return db.query(rol_permiso).filter(rol_permiso.c.permiso_id == permiso_id).first() is not None


def asignado_a_usuarios(db: Session, permiso_id: int) -> bool:
    """True si algún usuario tiene este permiso."""
    return db.query(usuario_permisos).filter(usuario_permisos.c.permiso_id == permiso_id).first() is not None
