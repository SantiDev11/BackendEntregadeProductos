# Consultas a la base de datos del módulo Empresas
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.modulos.bodegas.models import Bodega
from app.modulos.empresas.models import Empresa
from app.modulos.facturas.models import Orden
from app.modulos.roles.models import Rol
from app.modulos.usuarios.models import Usuario


def existe_nit(db: Session, nit: str) -> bool:
    """True si otra empresa ya tiene ese NIT (sin el dígito de verificación)."""
    return db.query(Empresa).filter(Empresa.nit == nit).first() is not None


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
