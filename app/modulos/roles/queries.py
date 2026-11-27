# Consultas a la base de datos del módulo Roles
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.modulos.bodegas.models import Bodega
from app.modulos.empresas.models import Empresa
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


def desactivar_usuarios(db: Session, rol_id: int) -> None:
    """Desactiva los usuarios activos del rol y los marca, para reactivar solo esos después. También marca a los que ya
    estaban inactivos por la suspensión de su empresa: si reactivan la empresa, siguen inactivos mientras el rol lo esté.
    Las bodegas que tenían a cargo quedan sin bodeguero (como al desactivar un bodeguero). No hace commit."""
    db.query(Usuario).filter(Usuario.rol_id == rol_id, or_(Usuario.estado.is_(True), Usuario.desactivado_por_empresa.is_(True))).update(
        {Usuario.estado: False, Usuario.desactivado_por_rol: True}, synchronize_session=False)
    del_rol = select(Usuario.id).where(Usuario.rol_id == rol_id, Usuario.desactivado_por_rol.is_(True))
    db.query(Bodega).filter(Bodega.bodeguero_id.in_(del_rol)).update({Bodega.bodeguero_id: None}, synchronize_session=False)


def reactivar_usuarios(db: Session, rol_id: int) -> None:
    """Vuelve a activar solo los usuarios que desactivó el rol. Si su empresa no está activa (suspendida, pendiente o
    rechazada), pasan a esperar a la empresa: siguen inactivos y los reactivará ella al quedar activa. No hace commit."""
    marcados = (Usuario.rol_id == rol_id, Usuario.desactivado_por_rol.is_(True))
    empresa_no_activa = Usuario.empresa_id.in_(select(Empresa.id).where(Empresa.estado != "activa"))
    db.query(Usuario).filter(*marcados, empresa_no_activa).update(
        {Usuario.desactivado_por_rol: False, Usuario.desactivado_por_empresa: True}, synchronize_session=False)
    db.query(Usuario).filter(*marcados).update({Usuario.estado: True, Usuario.desactivado_por_rol: False},
                                               synchronize_session=False)
