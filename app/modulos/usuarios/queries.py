# Consultas a la base de datos del módulo Usuarios
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload, selectinload

from app.modulos.facturas.models import Orden
from app.modulos.permisos.models import Permiso
from app.modulos.roles.models import Rol
from app.modulos.usuarios.models import Usuario


def obtener(db: Session, usuario_id: int) -> Usuario | None:
    """Usuario por id, o None si no existe."""
    return db.get(Usuario, usuario_id)


def obtener_rol(db: Session, rol_id: int) -> Rol | None:
    """Rol por id, o None si no existe."""
    return db.get(Rol, rol_id)


def obtener_permiso(db: Session, permiso_id: int) -> Permiso | None:
    """Permiso por id, o None si no existe."""
    return db.get(Permiso, permiso_id)


def existe_correo(db: Session, correo: str, excluir_id: int | None = None) -> bool:
    """True si otro usuario ya tiene ese correo (sin distinguir mayúsculas)."""
    query = db.query(Usuario).filter(func.lower(Usuario.correo) == correo.lower())
    if excluir_id is not None:
        query = query.filter(Usuario.id != excluir_id)  # al editar, no compararse consigo mismo
    return query.first() is not None


def existe_documento(db: Session, numero_documento: str, excluir_id: int | None = None) -> bool:
    """True si otro usuario ya tiene ese número de documento."""
    query = db.query(Usuario).filter(Usuario.numero_documento == numero_documento)
    if excluir_id is not None:
        query = query.filter(Usuario.id != excluir_id)  # al editar, no compararse consigo mismo
    return query.first() is not None


def listar(db: Session, q: str | None, estado: bool | None, rol: str | None, rol_id: int | None,
           page: int, limit: int) -> tuple[int, list[Usuario]]:
    """Devuelve (total que cumple los filtros, usuarios de la página con rol y permisos), ordenados por id."""
    query = db.query(Usuario)
    if rol:
        query = query.join(Usuario.rol).filter(func.lower(Rol.nombre) == rol.strip().lower())
    if q:
        # contiene, sin distinguir mayúsculas, en nombre o correo
        query = query.filter(or_(Usuario.nombre.ilike(f"%{q}%"), Usuario.correo.ilike(f"%{q}%")))
    if estado is not None:
        query = query.filter(Usuario.estado == estado)  # si no viene, devuelve activos e inactivos
    if rol_id is not None:
        query = query.filter(Usuario.rol_id == rol_id)

    total = query.count()  # total que cumple los filtros, antes de paginar
    usuarios = (
        query.options(joinedload(Usuario.rol), selectinload(Usuario.permisos))  # trae rol y permisos de una vez
        .order_by(Usuario.id)
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )
    return total, usuarios


def permisos_por_ids(db: Session, ids: set[int]) -> list[Permiso]:
    """Permisos cuyos ids están en la lista (los que no existan simplemente no vienen)."""
    return db.query(Permiso).filter(Permiso.id.in_(ids)).all() if ids else []


def tiene_facturas(db: Session, usuario_id: int) -> bool:
    """True si el usuario aparece en alguna factura, como cliente o como emisor."""
    return db.query(Orden).filter(or_(Orden.cliente_id == usuario_id, Orden.bodeguero_id == usuario_id)).first() is not None
