# Consultas a la base de datos del módulo Tipos
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.core.alcance import Alcance
from app.modulos.bodegas.models import Bodega
from app.modulos.facturas.models import OrdenDetalle
from app.modulos.tipos.models import Tipo


def obtener(db: Session, tipo_id: int) -> Tipo | None:
    """Tipo por id, o None si no existe."""
    return db.get(Tipo, tipo_id)


def existe_nombre(db: Session, nombre: str, bodega_id: int | None, excluir_id: int | None = None) -> bool:
    """True si ya hay un tipo con ese nombre en ESA bodega (sin distinguir mayúsculas), sin contar `excluir_id`.
    Los tipos sin bodega (bodega_id = None) se comparan entre sí."""
    query = db.query(Tipo).filter(func.lower(Tipo.nombre) == nombre.lower())
    query = query.filter(Tipo.bodega_id.is_(None) if bodega_id is None else Tipo.bodega_id == bodega_id)
    if excluir_id is not None:
        query = query.filter(Tipo.id != excluir_id)  # al editar, no compararse consigo mismo
    return query.first() is not None


def listar(db: Session, alcance: Alcance, q: str | None, estado: bool | None, bodega_id: int | None,
           bodegas_permitidas: list[int] | None, page: int, limit: int) -> tuple[int, list[Tipo]]:
    """Devuelve (total que cumple los filtros, tipos de la página con su bodega), ordenados por id.
    `bodegas_permitidas`: None = todas (admin); una lista = solo tipos de esas bodegas."""
    query = db.query(Tipo).filter(*alcance.condiciones(Tipo.empresa_id))
    if bodegas_permitidas is not None:
        query = query.filter(Tipo.bodega_id.in_(bodegas_permitidas))
    if bodega_id is not None:
        query = query.filter(Tipo.bodega_id == bodega_id)
    if q:
        query = query.filter(Tipo.nombre.ilike(f"%{q}%"))  # contiene, sin distinguir mayúsculas
    if estado is not None:
        query = query.filter(Tipo.estado == estado)  # si no viene, devuelve activos e inactivos

    total = query.count()  # total que cumple el filtro, antes de paginar
    tipos = (
        query.options(joinedload(Tipo.bodega))  # trae la bodega en la misma consulta
        .order_by(Tipo.id)
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )
    return total, tipos


def ids_bodegas(db: Session, alcance: Alcance) -> list[int]:
    """Ids de las bodegas del usuario, de menor a mayor: todas las de su empresa si es el rol empresa;
    si no, las de su empresa de las que es dueño."""
    query = db.query(Bodega.id).filter(*alcance.condiciones(Bodega.empresa_id))
    if not alcance.ve_toda_la_empresa:
        query = query.filter(Bodega.bodeguero_id == alcance.usuario.id)
    return [i for (i,) in query.order_by(Bodega.id).all()]


def obtener_bodega(db: Session, bodega_id: int) -> Bodega | None:
    """Bodega por id, o None si no existe."""
    return db.get(Bodega, bodega_id)


def usado_en_facturas(db: Session, tipo_id: int) -> bool:
    """True si alguna línea de factura usa este tipo."""
    return db.query(OrdenDetalle).filter(OrdenDetalle.tipo_id == tipo_id).first() is not None
