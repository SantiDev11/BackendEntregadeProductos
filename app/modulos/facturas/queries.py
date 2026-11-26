# Consultas a la base de datos del módulo Facturas
from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.mysql import insert
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.alcance import Alcance
from app.modulos.bodegas.models import Bodega
from app.modulos.facturas.emisor import PREFIJO_FACTURA, RESOLUCION
from app.modulos.facturas.models import ConsecutivoFactura, Orden
from app.modulos.roles.models import Rol
from app.modulos.tipos.models import Tipo
from app.modulos.usuarios.models import Usuario


def consulta_completa(db: Session):
    """Consulta de órdenes con bodega, bodeguero, empresa y líneas cargados de una vez."""
    return db.query(Orden).options(
        joinedload(Orden.bodega), joinedload(Orden.bodeguero), joinedload(Orden.empresa), selectinload(Orden.detalles)
    )


def obtener_completa(db: Session, factura_id: int) -> Orden | None:
    """Factura por id con todo lo necesario para la respuesta, o None si no existe."""
    return consulta_completa(db).filter(Orden.id == factura_id).first()


def condiciones_visibles(alcance: Alcance) -> list:
    """Condiciones de "facturas que puede ver" el usuario (la misma regla de helpers.puede_ver_factura):
    - cliente: las que creó + las que son para él (menos los borradores en `emitida`), de cualquier empresa.
    - admin y empresa: las de su alcance. Los demás: además, solo las que crearon."""
    usuario_id = alcance.usuario.id
    creadas = Orden.bodeguero_id == usuario_id  # bodeguero_id = quien creó la factura
    if alcance.usuario.rol.nombre == "cliente":
        return [or_(creadas, and_(Orden.cliente_id == usuario_id, Orden.estado_orden != "emitida"))]
    condiciones = alcance.condiciones(Orden.empresa_id)
    return condiciones if alcance.ve_toda_la_empresa else [*condiciones, creadas]


def listar(db: Session, alcance: Alcance, q: str | None, estado: str | None,
           page: int, limit: int) -> tuple[int, list[Orden]]:
    """Devuelve (total que cumple los filtros, facturas de la página), de la más reciente a la más antigua.
    Solo trae las facturas que el usuario puede ver según `alcance`."""
    query = db.query(Orden).join(Orden.cliente).filter(*condiciones_visibles(alcance))
    if q:
        query = query.filter(or_(Orden.numero.ilike(f"%{q}%"), Usuario.nombre.ilike(f"%{q}%")))
    if estado:
        query = query.filter(Orden.estado_orden == estado)

    total = query.count()  # total que cumple los filtros, antes de paginar
    ordenes = (
        query.options(joinedload(Orden.bodega), joinedload(Orden.bodeguero), joinedload(Orden.empresa))
        .order_by(Orden.id.desc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )
    return total, ordenes


def listar_clientes(db: Session, q: str | None, page: int, limit: int) -> tuple[int, list[Usuario]]:
    """DEPRECATED (GET /facturas/clientes): usar clientes.queries.buscar. Clientes activos, ordenados por nombre."""
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


def siguiente_consecutivo(db: Session, empresa_id: int | None) -> int:
    """Siguiente consecutivo de la empresa en el prefijo actual (empieza en el rango_desde de la resolución).
    Deja bloqueado el contador de la empresa hasta el commit: si otra petición numera al mismo tiempo, espera su turno.
    Un número ya entregado no se vuelve a usar, aunque la factura se elimine."""
    serie = empresa_id or 0
    # El máximo ya guardado solo importa si el contador no existe o quedó atrás (facturas que el backfill pasó a la empresa).
    # Puede ser una lectura vieja, pero nunca mayor que el contador de una factura numerada aquí
    ultimo = db.query(func.max(Orden.consecutivo)).filter(
        Orden.prefijo == PREFIJO_FACTURA,
        Orden.empresa_id.is_(None) if empresa_id is None else Orden.empresa_id == empresa_id,
    ).scalar()
    usado = ultimo or RESOLUCION["rango_desde"] - 1

    contador = insert(ConsecutivoFactura).values(serie=serie, prefijo=PREFIJO_FACTURA, ultimo=usado + 1)
    db.execute(contador.on_duplicate_key_update(ultimo=func.greatest(ConsecutivoFactura.ultimo, usado) + 1))
    return db.execute(select(ConsecutivoFactura.ultimo).where(
        ConsecutivoFactura.serie == serie, ConsecutivoFactura.prefijo == PREFIJO_FACTURA)).scalar_one()
