# Consultas a la base de datos del módulo Facturas
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, joinedload, selectinload

from app.modulos.bodegas.models import Bodega
from app.modulos.facturas.emisor import PREFIJO_FACTURA, RESOLUCION
from app.modulos.facturas.models import Orden
from app.modulos.roles.models import Rol
from app.modulos.tipos.models import Tipo
from app.modulos.usuarios.models import Usuario


def consulta_completa(db: Session):
    """Consulta de órdenes con bodega, bodeguero y líneas cargados de una vez."""
    return db.query(Orden).options(
        joinedload(Orden.bodega), joinedload(Orden.bodeguero), selectinload(Orden.detalles)
    )


def obtener_completa(db: Session, factura_id: int) -> Orden | None:
    """Factura por id con todo lo necesario para la respuesta, o None si no existe."""
    return consulta_completa(db).filter(Orden.id == factura_id).first()


def filtro_dueno(alcance: str, usuario_id: int):
    """Condición de "facturas que puede ver" según el alcance (ver helpers.alcance_facturas).
    Devuelve None cuando puede ver todas."""
    if alcance == "todas":
        return None
    creadas = Orden.bodeguero_id == usuario_id  # bodeguero_id = quien creó la factura
    if alcance == "cliente":
        # las que creó + las que son para él (menos los borradores en `emitida`)
        return or_(creadas, and_(Orden.cliente_id == usuario_id, Orden.estado_orden != "emitida"))
    return creadas


def listar(db: Session, alcance: str, usuario_id: int, q: str | None, estado: str | None,
           page: int, limit: int) -> tuple[int, list[Orden]]:
    """Devuelve (total que cumple los filtros, facturas de la página), de la más reciente a la más antigua.
    Solo trae las facturas que el usuario puede ver según `alcance`."""
    query = db.query(Orden).join(Orden.cliente)
    condicion = filtro_dueno(alcance, usuario_id)
    if condicion is not None:
        query = query.filter(condicion)
    if q:
        query = query.filter(or_(Orden.numero.ilike(f"%{q}%"), Usuario.nombre.ilike(f"%{q}%")))
    if estado:
        query = query.filter(Orden.estado_orden == estado)

    total = query.count()  # total que cumple los filtros, antes de paginar
    ordenes = (
        query.options(joinedload(Orden.bodega), joinedload(Orden.bodeguero))
        .order_by(Orden.id.desc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )
    return total, ordenes


def listar_clientes(db: Session, q: str | None, page: int, limit: int) -> tuple[int, list[Usuario]]:
    """Clientes activos (para el selector de la factura), ordenados por nombre."""
    query = db.query(Usuario).join(Usuario.rol).filter(Rol.nombre == "cliente", Usuario.estado.is_(True))
    if q:
        query = query.filter(or_(Usuario.nombre.ilike(f"%{q}%"), Usuario.numero_documento.ilike(f"%{q}%")))

    total = query.count()
    clientes = query.order_by(Usuario.nombre).offset((page - 1) * limit).limit(limit).all()
    return total, clientes


def cliente_activo(db: Session, cliente_id: int) -> Usuario | None:
    """Usuario con rol cliente y activo con ese id, o None."""
    return db.query(Usuario).join(Usuario.rol).filter(
        Usuario.id == cliente_id, Rol.nombre == "cliente", Usuario.estado.is_(True)
    ).first()


def obtener_bodega(db: Session, bodega_id: int) -> Bodega | None:
    """Bodega por id, o None si no existe."""
    return db.get(Bodega, bodega_id)


def tipos_por_ids(db: Session, ids: set[int]) -> list[Tipo]:
    """Tipos cuyos ids están en la lista (los que no existan simplemente no vienen)."""
    return db.query(Tipo).filter(Tipo.id.in_(ids)).all()


def siguiente_consecutivo(db: Session) -> int:
    """Siguiente consecutivo del prefijo actual (empieza en el rango_desde de la resolución)."""
    ultimo = db.query(func.max(Orden.consecutivo)).filter(Orden.prefijo == PREFIJO_FACTURA).scalar()
    return (ultimo or RESOLUCION["rango_desde"] - 1) + 1
