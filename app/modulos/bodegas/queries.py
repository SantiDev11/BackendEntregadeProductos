# Consultas a la base de datos del módulo Bodegas
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.core.alcance import Alcance
from app.modulos.bodegas.models import Bodega
from app.modulos.facturas.models import Orden
from app.modulos.roles.models import Rol
from app.modulos.tipos.models import Tipo
from app.modulos.usuarios.models import Usuario


def obtener(db: Session, bodega_id: int) -> Bodega | None:
    """Bodega por id, o None si no existe."""
    return db.get(Bodega, bodega_id)


def existe_nombre(db: Session, nombre: str, excluir_id: int | None = None) -> bool:
    """True si ya hay una bodega con ese nombre (sin distinguir mayúsculas), sin contar `excluir_id`."""
    query = db.query(Bodega).filter(func.lower(Bodega.nombre) == nombre.lower())
    if excluir_id is not None:
        query = query.filter(Bodega.id != excluir_id)  # al editar, no compararse consigo misma
    return query.first() is not None


def existe_codigo(db: Session, codigo: str, excluir_id: int | None = None) -> bool:
    """True si ya hay una bodega con ese código (sin distinguir mayúsculas), sin contar `excluir_id`."""
    query = db.query(Bodega).filter(func.lower(Bodega.codigo) == codigo.lower())
    if excluir_id is not None:
        query = query.filter(Bodega.id != excluir_id)  # al editar, no compararse consigo misma
    return query.first() is not None


def obtener_bodeguero(db: Session, usuario_id: int) -> Usuario | None:
    """El usuario si existe y tiene rol bodeguero; si no, None."""
    return db.query(Usuario).join(Usuario.rol).filter(Usuario.id == usuario_id, Rol.nombre == "bodeguero").first()


def listar(db: Session, alcance: Alcance, q: str | None, estado: bool | None, bodeguero_id: int | None,
           page: int, limit: int) -> tuple[int, list[Bodega]]:
    """Devuelve (total que cumple los filtros, bodegas de la página con su dueño), ordenadas por id."""
    query = db.query(Bodega).filter(*alcance.condiciones(Bodega.empresa_id))
    if q:
        query = query.filter(Bodega.nombre.ilike(f"%{q}%"))  # contiene, sin distinguir mayúsculas
    if estado is not None:
        query = query.filter(Bodega.estado == estado)  # si no viene, devuelve activas e inactivas
    if bodeguero_id is not None:
        query = query.filter(Bodega.bodeguero_id == bodeguero_id)

    total = query.count()  # total que cumple los filtros, antes de paginar
    bodegas = (
        query.options(joinedload(Bodega.bodeguero))  # trae el dueño en la misma consulta
        .order_by(Bodega.id)
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )
    return total, bodegas


def tiene_facturas(db: Session, bodega_id: int) -> bool:
    """True si alguna factura sale de esta bodega."""
    return db.query(Orden).filter(Orden.bodega_id == bodega_id).first() is not None


def tiene_tipos(db: Session, bodega_id: int) -> bool:
    """True si la bodega tiene tipos en su catálogo."""
    return db.query(Tipo).filter(Tipo.bodega_id == bodega_id).first() is not None
