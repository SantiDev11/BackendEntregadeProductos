# Consultas a la base de datos del módulo Estadísticas (conteos y sumas sobre las facturas).
# Todas reciben `condiciones`: el periodo y el filtro de dueño (qué facturas puede contar el usuario).
from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.alcance import Alcance
from app.modulos.bodegas.models import Bodega
from app.modulos.empresas.models import Empresa
from app.modulos.facturas.models import Orden, OrdenDetalle
from app.modulos.facturas.queries import condiciones_visibles
from app.modulos.roles.models import Rol
from app.modulos.tipos.models import Tipo
from app.modulos.usuarios.models import Usuario

NO_SUMAN = "rechazada"  # las facturas rechazadas no cuentan en lo facturado

# Grupos de estados de la factura (los mismos nombres que usa el filtro ?estado=)
PENDIENTES, COMPLETADAS, RECHAZADAS = ("emitida", "entregada"), ("firmada", "recibida"), ("rechazada",)
GRUPOS = {"pendientes": PENDIENTES, "completadas": COMPLETADAS, "aceptadas": COMPLETADAS, "rechazadas": RECHAZADAS}
SIN_EMPRESA = "Sin empresa"  # facturas anteriores a las empresas


def condiciones_facturas(alcance: Alcance, desde: date, hasta: date) -> list:
    """Facturas emitidas entre `desde` y `hasta` (ambos incluidos) que el usuario puede ver
    (la misma regla de dueño de GET /facturas)."""
    return [
        Orden.fecha_emision >= datetime.combine(desde, time.min),
        Orden.fecha_emision <= datetime.combine(hasta, time.max.replace(microsecond=0)),
        *condiciones_visibles(alcance),
    ]


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


def usuarios_activos(db: Session, alcance: Alcance) -> int:
    return db.query(func.count(Usuario.id)).filter(Usuario.estado.is_(True), *alcance.condiciones(Usuario.empresa_id)).scalar()


def bodegas_activas(db: Session, alcance: Alcance) -> int:
    return db.query(func.count(Bodega.id)).filter(Bodega.estado.is_(True), *alcance.condiciones(Bodega.empresa_id)).scalar()


def bodegueros(db: Session, alcance: Alcance) -> int:
    """Cuántos bodegueros hay en la empresa."""
    return (db.query(func.count(Usuario.id)).join(Rol, Usuario.rol_id == Rol.id)
            .filter(Rol.nombre == "bodeguero", *alcance.condiciones(Usuario.empresa_id)).scalar())


def bodegas_del_usuario(db: Session, alcance: Alcance) -> list[int]:
    """Ids de las bodegas del usuario: todas las de su empresa si es el rol empresa; si no, de las que es dueño."""
    query = db.query(Bodega.id).filter(*alcance.condiciones(Bodega.empresa_id))
    if not alcance.ve_toda_la_empresa:
        query = query.filter(Bodega.bodeguero_id == alcance.usuario.id)
    return [i for (i,) in query.all()]


def tipos_en_bodegas(db: Session, bodegas_ids: list[int]) -> int:
    """Cuántos tipos hay en el catálogo de esas bodegas."""
    if not bodegas_ids:
        return 0
    return db.query(func.count(Tipo.id)).filter(Tipo.bodega_id.in_(bodegas_ids)).scalar()


# ===== PANEL POR ROL =====

def obtener_bodega(db: Session, bodega_id: int) -> Bodega | None:
    return db.get(Bodega, bodega_id)


def condiciones_panel(alcance: Alcance, perfil: str, f, desde: date, hasta: date) -> list:
    """Las facturas del panel: el periodo y lo que el usuario puede ver (condiciones_facturas) MÁS los filtros pedidos.
    Los filtros solo reducen: nunca abren algo fuera del alcance. `f` son los Filtros ya validados."""
    condiciones = condiciones_facturas(alcance, desde, hasta)
    if perfil == "cliente":
        condiciones.append(Orden.cliente_id == alcance.usuario.id)  # solo las que son para él
        if f.empresa_id is not None:
            condiciones.append(Orden.empresa_id == f.empresa_id)
    if f.bodega_id is not None:
        condiciones.append(Orden.bodega_id == f.bodega_id)
    if f.bodeguero_id is not None:
        condiciones.append(Orden.bodeguero_id == f.bodeguero_id)
    if f.tipo_id is not None:
        condiciones.append(Orden.detalles.any(OrdenDetalle.tipo_id == f.tipo_id))
    if f.estado is not None:
        condiciones.append(Orden.empresa_id.in_(select(Empresa.id).where(Empresa.estado == f.estado)) if perfil == "admin"
                           else Orden.estado_orden.in_(GRUPOS[f.estado]))
    return condiciones


def _sumar(estados: tuple[str, ...]):
    """Cuántas de las facturas agrupadas están en esos estados."""
    return func.coalesce(func.sum(case((Orden.estado_orden.in_(estados), 1), else_=0)), 0)


def _agrupadas(columna, condiciones: list):
    """Subconsulta {clave, total, completadas, rechazadas} de las facturas, agrupadas por la columna."""
    return (select(columna.label("clave"), func.count(Orden.id).label("total"), _sumar(COMPLETADAS).label("completadas"),
                   _sumar(RECHAZADAS).label("rechazadas")).where(*condiciones).group_by(columna).subquery())


def por_empresa(db: Session, alcance: Alcance, condiciones: list, estado: str | None, limite: int = 10) -> list[tuple]:
    """[(empresa, bodegas, facturas, completadas, rechazadas)]: las de más facturas primero, aunque no tengan ninguna."""
    n = _agrupadas(Orden.empresa_id, condiciones)
    bodegas = select(func.count(Bodega.id)).where(Bodega.empresa_id == Empresa.id).correlate(Empresa).scalar_subquery()
    total = func.coalesce(n.c.total, 0)
    consulta = (select(Empresa.razon_social, bodegas, total, func.coalesce(n.c.completadas, 0), func.coalesce(n.c.rechazadas, 0))
                .outerjoin(n, n.c.clave == Empresa.id).where(*alcance.condiciones(Empresa.id)))
    if estado is not None:
        consulta = consulta.where(Empresa.estado == estado)
    return db.execute(consulta.order_by(total.desc(), Empresa.razon_social, Empresa.id).limit(limite)).all()


def por_bodega(db: Session, alcance: Alcance, condiciones: list, bodega_id: int | None) -> list[tuple]:
    """[(bodega, facturas, completadas, rechazadas)] de las bodegas de la empresa, aunque no tengan facturas."""
    n = _agrupadas(Orden.bodega_id, condiciones)
    total = func.coalesce(n.c.total, 0)
    consulta = (select(Bodega.nombre, total, func.coalesce(n.c.completadas, 0), func.coalesce(n.c.rechazadas, 0))
                .outerjoin(n, n.c.clave == Bodega.id).where(*alcance.condiciones(Bodega.empresa_id)))
    if bodega_id is not None:
        consulta = consulta.where(Bodega.id == bodega_id)
    return db.execute(consulta.order_by(total.desc(), Bodega.nombre, Bodega.id)).all()


def por_tipo(db: Session, condiciones: list, tipo_id: int | None) -> list[tuple]:
    """[(tipo, facturas, completadas, rechazadas)]: cada factura cuenta una vez por tipo, aunque lo repita en sus líneas."""
    def facturas(estados):
        return func.count(case((Orden.estado_orden.in_(estados), Orden.id)).distinct())

    total = func.count(Orden.id.distinct())
    consulta = (select(Tipo.nombre, total, facturas(COMPLETADAS), facturas(RECHAZADAS)).select_from(OrdenDetalle)
                .join(Orden, OrdenDetalle.orden_id == Orden.id).join(Tipo, OrdenDetalle.tipo_id == Tipo.id).where(*condiciones))
    if tipo_id is not None:
        consulta = consulta.where(Tipo.id == tipo_id)
    return db.execute(consulta.group_by(Tipo.id, Tipo.nombre).order_by(total.desc(), Tipo.nombre, Tipo.id)).all()


def por_proveedora(db: Session, condiciones: list) -> list[tuple]:
    """[(empresa, facturas, aceptadas, rechazadas)] de las empresas que le facturaron al cliente."""
    total = func.count(Orden.id)
    return db.execute(select(func.coalesce(Empresa.razon_social, SIN_EMPRESA), total, _sumar(COMPLETADAS), _sumar(RECHAZADAS))
                      .select_from(Orden).outerjoin(Empresa, Orden.empresa_id == Empresa.id).where(*condiciones)
                      .group_by(Orden.empresa_id, Empresa.razon_social)
                      .order_by(total.desc(), Empresa.razon_social)).all()


def por_dia(db: Session, condiciones: list) -> dict[date, tuple[int, int]]:
    """{día de emisión: (completadas, rechazadas)}."""
    dia = func.date(Orden.fecha_emision)
    filas = db.execute(select(dia, _sumar(COMPLETADAS), _sumar(RECHAZADAS)).where(*condiciones).group_by(dia)).all()
    return {d: (int(c), int(r)) for d, c, r in filas}


def ultimas_rechazadas(db: Session, condiciones: list, limite: int = 5) -> list[tuple]:
    """[(id, número, motivo, fecha del rechazo)], de la más reciente a la más antigua."""
    fecha = func.coalesce(Orden.fecha_respuesta, Orden.fecha_emision)
    return db.execute(select(Orden.id, Orden.numero, Orden.motivo_rechazo, fecha)
                      .where(*condiciones, Orden.estado_orden.in_(RECHAZADAS))
                      .order_by(fecha.desc(), Orden.id.desc()).limit(limite)).all()


def empresas_por_estado(db: Session) -> dict[str, int]:
    return dict(db.execute(select(Empresa.estado, func.count(Empresa.id)).group_by(Empresa.estado)).all())


def clientes_registrados(db: Session) -> int:
    return db.scalar(select(func.count(Usuario.id)).join(Rol, Usuario.rol_id == Rol.id).where(Rol.nombre == "cliente"))


def empresas_proveedoras(db: Session, condiciones: list) -> int:
    return db.scalar(select(func.count(Orden.empresa_id.distinct())).where(*condiciones))


# ===== OPCIONES DE LOS FILTROS =====
# [(id, nombre)] por nombre. No dependen del periodo ni de los demás filtros.

def opciones_empresas(db: Session) -> list[tuple]:
    return db.execute(select(Empresa.id, Empresa.razon_social).order_by(Empresa.razon_social, Empresa.id)).all()


def opciones_proveedoras(db: Session, alcance: Alcance) -> list[tuple]:
    """Las empresas que ya le facturaron al cliente (sin contar los borradores, que no ve)."""
    suyas = select(Orden.empresa_id).where(*condiciones_visibles(alcance), Orden.cliente_id == alcance.usuario.id)
    return db.execute(select(Empresa.id, Empresa.razon_social).where(Empresa.id.in_(suyas))
                      .order_by(Empresa.razon_social, Empresa.id)).all()


def opciones_bodegas(db: Session, alcance: Alcance) -> list[tuple]:
    return db.execute(select(Bodega.id, Bodega.nombre).where(*alcance.condiciones(Bodega.empresa_id))
                      .order_by(Bodega.nombre, Bodega.id)).all()


def opciones_bodegueros(db: Session, alcance: Alcance) -> list[tuple]:
    return db.execute(select(Usuario.id, Usuario.nombre).join(Rol, Usuario.rol_id == Rol.id)
                      .where(Rol.nombre == "bodeguero", *alcance.condiciones(Usuario.empresa_id))
                      .order_by(Usuario.nombre, Usuario.id)).all()


def opciones_tipos(db: Session, bodegas_ids: list[int]) -> list[tuple]:
    """Los tipos del catálogo de esas bodegas."""
    return db.execute(select(Tipo.id, Tipo.nombre).where(Tipo.bodega_id.in_(bodegas_ids)).order_by(Tipo.nombre, Tipo.id)).all()
