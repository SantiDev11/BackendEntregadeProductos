# Consultas a la base de datos del módulo Estadísticas (conteos y sumas sobre las facturas).
# Todas reciben `condiciones`: el periodo y el filtro de dueño (qué facturas puede contar el usuario).
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.modulos.bodegas.models import Bodega
from app.modulos.facturas.models import Orden, OrdenDetalle
from app.modulos.facturas.queries import filtro_dueno
from app.modulos.tipos.models import Tipo
from app.modulos.usuarios.models import Usuario

NO_SUMAN = "rechazada"  # las facturas rechazadas no cuentan en lo facturado


def condiciones_facturas(alcance: str, usuario_id: int, desde: date, hasta: date) -> list:
    """Facturas emitidas entre `desde` y `hasta` (ambos incluidos) que el usuario puede ver
    (la misma regla de dueño de GET /facturas)."""
    condiciones = [
        Orden.fecha_emision >= datetime.combine(desde, time.min),
        Orden.fecha_emision < datetime.combine(hasta + timedelta(days=1), time.min),
    ]
    dueno = filtro_dueno(alcance, usuario_id)
    if dueno is not None:
        condiciones.append(dueno)
    return condiciones


def conteo_por_estado(db: Session, condiciones: list) -> dict[str, int]:
    """{estado: cantidad de facturas}."""
    filas = db.query(Orden.estado_orden, func.count(Orden.id)).filter(*condiciones).group_by(Orden.estado_orden).all()
    return {estado: cantidad for estado, cantidad in filas}


def total_facturado(db: Session, condiciones: list) -> Decimal:
    """Suma del total de las facturas (sin las rechazadas)."""
    return db.query(func.coalesce(func.sum(Orden.total), 0)).filter(*condiciones, Orden.estado_orden != NO_SUMAN).scalar()


def facturas_por_dia(db: Session, condiciones: list) -> dict[date, int]:
    """{día: cantidad de facturas}."""
    dia = func.date(Orden.fecha_emision)
    return {d: n for d, n in db.query(dia, func.count(Orden.id)).filter(*condiciones).group_by(dia).all()}


def facturado_por_bodega(db: Session, condiciones: list) -> list[tuple[str, Decimal]]:
    """[(nombre de la bodega, facturado)] de mayor a menor (sin las rechazadas)."""
    suma = func.sum(Orden.total)
    return (db.query(Bodega.nombre, suma).join(Bodega, Orden.bodega_id == Bodega.id)
            .filter(*condiciones, Orden.estado_orden != NO_SUMAN)
            .group_by(Bodega.id, Bodega.nombre).order_by(suma.desc()).all())


def productos_mas_vendidos(db: Session, condiciones: list, limite: int = 5) -> list[tuple[str, Decimal]]:
    """[(nombre del tipo, cantidad vendida)] de mayor a menor (sin las rechazadas). Las líneas sin tipo no cuentan."""
    cantidad = func.sum(OrdenDetalle.cantidad)
    return (db.query(Tipo.nombre, cantidad).select_from(OrdenDetalle)
            .join(Orden, OrdenDetalle.orden_id == Orden.id)
            .join(Tipo, OrdenDetalle.tipo_id == Tipo.id)
            .filter(*condiciones, Orden.estado_orden != NO_SUMAN)
            .group_by(Tipo.id, Tipo.nombre).order_by(cantidad.desc()).limit(limite).all())


def usuarios_activos(db: Session) -> int:
    return db.query(func.count(Usuario.id)).filter(Usuario.estado.is_(True)).scalar()


def bodegas_activas(db: Session) -> int:
    return db.query(func.count(Bodega.id)).filter(Bodega.estado.is_(True)).scalar()


def bodegas_del_usuario(db: Session, usuario_id: int) -> list[int]:
    """Ids de las bodegas que le pertenecen al usuario."""
    return [i for (i,) in db.query(Bodega.id).filter(Bodega.bodeguero_id == usuario_id).all()]


def tipos_en_bodegas(db: Session, bodegas_ids: list[int]) -> int:
    """Cuántos tipos hay en el catálogo de esas bodegas."""
    if not bodegas_ids:
        return 0
    return db.query(func.count(Tipo.id)).filter(Tipo.bodega_id.in_(bodegas_ids)).scalar()
