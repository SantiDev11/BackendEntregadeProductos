# Consultas a la base de datos del módulo Empresas
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.modulos.bodegas.models import Bodega
from app.modulos.empresas.models import Empresa
from app.modulos.facturas.models import ConsecutivoFactura, Orden, OrdenDetalle
from app.modulos.roles.models import Rol
from app.modulos.tipos.models import Tipo
from app.modulos.usuarios.models import Usuario


def existe_nit(db: Session, nit: str, excluir_id: int | None = None) -> bool:
    """True si otra empresa ya tiene ese NIT (sin el dígito de verificación)."""
    query = db.query(Empresa).filter(Empresa.nit == nit)
    if excluir_id is not None:
        query = query.filter(Empresa.id != excluir_id)  # al editar, no compararse consigo misma
    return query.first() is not None


def obtener(db: Session, empresa_id: int) -> Empresa | None:
    """Empresa por id, o None si no existe."""
    return db.get(Empresa, empresa_id)


def listar(db: Session, q: str | None, estado: str | None, page: int, limit: int) -> tuple[int, list[Empresa]]:
    """Devuelve (total que cumple los filtros, empresas de la página), de la más reciente a la más antigua."""
    query = db.query(Empresa)
    if q:
        texto = f"%{q}%"  # contiene, sin distinguir mayúsculas
        query = query.filter(or_(Empresa.razon_social.ilike(texto), Empresa.correo.ilike(texto),
                                 func.concat(Empresa.nit, "-", func.coalesce(Empresa.dv, "")).ilike(texto)))
    if estado is not None:
        query = query.filter(Empresa.estado == estado)

    total = query.count()  # total que cumple los filtros, antes de paginar
    empresas = query.order_by(Empresa.id.desc()).offset((page - 1) * limit).limit(limit).all()
    return total, empresas


def _usuarios(empresa_id: int):
    """Todos los usuarios de la empresa (su usuario empresa, sus bodegueros y los de otros roles): se van con ella."""
    return select(Usuario.id).where(Usuario.empresa_id == empresa_id)


def _bodegas(empresa_id: int):
    return select(Bodega.id).where(Bodega.empresa_id == empresa_id)


def _tipos(empresa_id: int):
    return select(Tipo.id).where(or_(Tipo.empresa_id == empresa_id, Tipo.bodega_id.in_(_bodegas(empresa_id))))


def lo_que_impide_eliminar(db: Session, empresa_id: int) -> list[str]:
    """Qué impide eliminar la empresa (lista vacía si nada):
    - facturas: de la empresa, de sus bodegas, creadas por sus usuarios, a nombre de ellos o con sus tipos en el detalle;
    - bodegas de otra empresa a cargo de uno de sus usuarios (solo pasa si el admin las movió): no se borran ajenas."""
    usuarios, bodegas, tipos = _usuarios(empresa_id), _bodegas(empresa_id), _tipos(empresa_id)
    revisiones = [
        ("facturas", select(Orden.id).where(or_(Orden.empresa_id == empresa_id, Orden.bodega_id.in_(bodegas),
                                                Orden.bodeguero_id.in_(usuarios), Orden.cliente_id.in_(usuarios)))),
        ("facturas", select(OrdenDetalle.id).where(OrdenDetalle.tipo_id.in_(tipos))),
        ("bodegas de otra empresa a cargo de sus usuarios",
         select(Bodega.id).where(Bodega.bodeguero_id.in_(usuarios), or_(Bodega.empresa_id.is_(None), Bodega.empresa_id != empresa_id))),
    ]
    encontrados = [nombre for nombre, consulta in revisiones if db.execute(consulta.limit(1)).first() is not None]
    return list(dict.fromkeys(encontrados))  # sin repetidos, en orden


def bloquear(db: Session, empresa_id: int) -> None:
    """Bloquea la fila de la empresa hasta el commit: mientras se borra, nadie puede crearle usuarios, bodegas ni tipos."""
    db.query(Empresa.id).filter(Empresa.id == empresa_id).with_for_update().one()


def eliminar(db: Session, empresa: Empresa) -> dict[str, int]:
    """Elimina la empresa con sus tipos, bodegas, usuarios (y sus permisos, por cascada) y su contador de facturas.
    Devuelve cuántos de cada uno se borraron. No hace commit."""
    i = empresa.id
    tipos = [fila.id for fila in db.execute(_tipos(i))]  # MySQL no deja borrar de tipos con una subconsulta sobre bodegas y tipos

    def borrar(modelo, *condicion):
        return db.query(modelo).filter(*condicion).delete(synchronize_session=False)

    borrados = {
        "tipos": borrar(Tipo, Tipo.id.in_(tipos)) if tipos else 0,  # primero: apuntan a las bodegas
        "bodegas": borrar(Bodega, Bodega.empresa_id == i),          # luego: apuntan a los bodegueros
        "usuarios": borrar(Usuario, Usuario.empresa_id == i),
    }
    borrar(ConsecutivoFactura, ConsecutivoFactura.serie == i)
    db.delete(empresa)
    db.flush()
    return borrados


def totales(db: Session, ids: list[int]) -> dict[int, dict[str, int]]:
    """{empresa_id: {total_bodegueros, total_bodegas, total_facturas}} en tres consultas, sin importar cuántas empresas sean."""
    def contar(columna, *condiciones):
        consulta = select(columna, func.count()).where(columna.in_(ids), *condiciones).group_by(columna)
        return dict(db.execute(consulta).all())

    bodegueros = contar(Usuario.empresa_id, Usuario.rol_id.in_(select(Rol.id).where(Rol.nombre == "bodeguero")))
    bodegas = contar(Bodega.empresa_id)
    facturas = contar(Orden.empresa_id)
    return {i: {"total_bodegueros": bodegueros.get(i, 0), "total_bodegas": bodegas.get(i, 0),
                "total_facturas": facturas.get(i, 0)} for i in ids}
