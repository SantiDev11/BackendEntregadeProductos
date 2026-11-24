# Lógica de cada endpoint de Empresas. El router solo recibe la petición y llama a estas funciones.
from sqlalchemy.orm import Session

from app.modulos.empresas import errors, queries
from app.modulos.empresas.helpers import empresa_salida, get_empresa_or_404, validate_cambio_estado
from app.modulos.empresas.models import ESTADOS_EMPRESA
from app.modulos.empresas.schemas import EmpresaEstadoUpdate, EmpresaOut, EmpresaPaginado


def listar(db: Session, q: str | None, estado: str | None, page: int, limit: int) -> EmpresaPaginado:
    """Lista las empresas con búsqueda, filtro por estado, paginación y sus totales."""
    if estado is not None:
        estado = estado.strip().lower()
        if estado not in ESTADOS_EMPRESA:
            raise errors.filtro_estado_invalido()

    total, empresas = queries.listar(db, q=q, estado=estado, page=page, limit=limit)
    totales = queries.totales(db, [e.id for e in empresas])
    return EmpresaPaginado(data=[empresa_salida(e, totales[e.id]) for e in empresas], total=total, page=page, limit=limit)


def cambiar_estado(db: Session, empresa_id: int, datos: EmpresaEstadoUpdate) -> EmpresaOut:
    """Aprueba, rechaza, suspende o reactiva una empresa. El motivo solo se guarda al rechazar."""
    empresa = get_empresa_or_404(db, empresa_id)
    validate_cambio_estado(empresa.estado, datos.estado)

    empresa.estado = datos.estado
    empresa.motivo_rechazo = datos.motivo_rechazo  # el schema lo deja en None si no es un rechazo
    db.commit()
    db.refresh(empresa)
    return empresa_salida(empresa, queries.totales(db, [empresa.id])[empresa.id])
