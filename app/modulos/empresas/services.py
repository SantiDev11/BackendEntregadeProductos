# Lógica de cada endpoint de Empresas. El router solo recibe la petición y llama a estas funciones.
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modulos.empresas import errors, queries
from app.modulos.empresas.helpers import (empresa_salida, get_empresa_or_404, validate_cambio_estado, validate_se_puede_eliminar,
                                          validate_unique_nit)
from app.modulos.empresas.models import ESTADOS_EMPRESA, Empresa
from app.modulos.empresas.schemas import EmpresaCreate, EmpresaEstadoUpdate, EmpresaOut, EmpresaPaginado, EmpresaUpdate
from app.modulos.registro.services import crear_empresa, guardar_todo_o_nada
from app.modulos.usuarios.models import Usuario


def _con_totales(db: Session, empresa: Empresa) -> EmpresaOut:
    return empresa_salida(empresa, queries.totales(db, [empresa.id])[empresa.id])


def listar(db: Session, q: str | None, estado: str | None, page: int, limit: int) -> EmpresaPaginado:
    """Lista las empresas con búsqueda, filtro por estado, paginación y sus totales."""
    if estado is not None:
        estado = estado.strip().lower()
        if estado not in ESTADOS_EMPRESA:
            raise errors.filtro_estado_invalido()

    total, empresas = queries.listar(db, q=q, estado=estado, page=page, limit=limit)
    totales = queries.totales(db, [e.id for e in empresas])
    return EmpresaPaginado(data=[empresa_salida(e, totales[e.id]) for e in empresas], total=total, page=page, limit=limit)


def obtener(db: Session, empresa_id: int) -> EmpresaOut:
    """Devuelve una empresa por su id, con sus totales."""
    return _con_totales(db, get_empresa_or_404(db, empresa_id))


def crear(db: Session, datos: EmpresaCreate, admin: Usuario) -> EmpresaOut:
    """Crea la empresa ya activa y su usuario, en una transacción: con los mismos datos y validaciones del registro público."""
    empresa = guardar_todo_o_nada(db, datos, lambda: crear_empresa(db, datos, "activa", creado_por=admin.id))
    return _con_totales(db, empresa)


def actualizar(db: Session, empresa_id: int, datos: EmpresaUpdate) -> EmpresaOut:
    """Actualiza solo los campos enviados (los que lleguen en null se ignoran). No cambia el estado ni su usuario."""
    empresa = get_empresa_or_404(db, empresa_id)
    cambios = datos.model_dump(exclude_none=True)
    if "nit" in cambios:
        cambios["nit"], cambios["dv"] = cambios["nit"].split("-")
        validate_unique_nit(db, cambios["nit"], excluir_id=empresa_id)

    for campo, valor in cambios.items():
        setattr(empresa, campo, valor)
    try:
        db.commit()
    except IntegrityError:
        # Otra petición guardó el mismo NIT al mismo tiempo
        db.rollback()
        validate_unique_nit(db, cambios.get("nit", ""), excluir_id=empresa_id)
        raise
    return _con_totales(db, empresa)


def eliminar(db: Session, empresa_id: int) -> None:
    """Elimina la empresa con todos sus usuarios, bodegas y tipos, si no tiene facturas."""
    empresa = get_empresa_or_404(db, empresa_id)
    queries.bloquear(db, empresa_id)  # desde aquí nadie le agrega usuarios, bodegas ni tipos
    validate_se_puede_eliminar(db, empresa_id)
    try:
        queries.eliminar(db, empresa)
        db.commit()
    except IntegrityError:
        # Algo que la revisión no vio (por ejemplo, una factura creada al mismo tiempo): la base no dejó borrar
        db.rollback()
        validate_se_puede_eliminar(db, empresa_id)
        raise errors.cambio_al_eliminar()


def cambiar_estado(db: Session, empresa_id: int, datos: EmpresaEstadoUpdate) -> EmpresaOut:
    """Aprueba, rechaza, suspende o reactiva una empresa. El motivo solo se guarda al rechazar.
    Suspenderla desactiva sus usuarios, bodegas y tipos; reactivarla devuelve a activo solo lo que desactivó la suspensión."""
    empresa = get_empresa_or_404(db, empresa_id)
    validate_cambio_estado(empresa.estado, datos.estado)

    if datos.estado == "suspendida":
        queries.suspender_en_cascada(db, empresa_id)
    elif datos.estado == "activa":
        queries.reactivar_en_cascada(db, empresa_id)
    empresa.estado = datos.estado
    empresa.motivo_rechazo = datos.motivo_rechazo  # el schema lo deja en None si no es un rechazo
    db.commit()
    db.refresh(empresa)
    return _con_totales(db, empresa)
