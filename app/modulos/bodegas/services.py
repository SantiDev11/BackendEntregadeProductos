# Lógica de cada endpoint de Bodegas. El router solo recibe la petición y llama a estas funciones.
# El usuario que no es admin solo ve y maneja las bodegas que le pertenecen.
from sqlalchemy.orm import Session

from app.modulos.bodegas import queries
from app.modulos.bodegas.helpers import (es_admin, get_bodega_or_404, validate_bodeguero, validate_se_puede_eliminar,
                                         validate_unique_bodega_codigo, validate_unique_bodega_name)
from app.modulos.bodegas.models import Bodega
from app.modulos.bodegas.schemas import BodegaCreate, BodegaOut, BodegaPaginado, BodegaUpdate
from app.modulos.usuarios.models import Usuario


def listar(db: Session, usuario: Usuario, q: str | None, estado: bool | None, bodeguero_id: int | None,
           page: int, limit: int) -> BodegaPaginado:
    """Lista las bodegas con búsqueda, filtros y paginación. El bodeguero solo ve las suyas."""
    if not es_admin(usuario):
        bodeguero_id = usuario.id  # el bodeguero siempre ve solo sus bodegas

    total, bodegas = queries.listar(db, q=q, estado=estado, bodeguero_id=bodeguero_id, page=page, limit=limit)
    return BodegaPaginado(
        data=[BodegaOut.model_validate(b) for b in bodegas],
        total=total,
        page=page,
        limit=limit,
    )


def obtener(db: Session, bodega_id: int, usuario: Usuario) -> Bodega:
    """Devuelve una bodega por su id (el bodeguero solo las suyas)."""
    return get_bodega_or_404(db, bodega_id, usuario)


def crear(db: Session, datos: BodegaCreate, usuario: Usuario) -> Bodega:
    """Crea una bodega nueva, define su dueño y registra quién la creó."""
    validate_unique_bodega_name(db, datos.nombre)

    valores = datos.model_dump()
    valores["codigo"] = valores["codigo"].upper()  # el código siempre se guarda en mayúsculas
    validate_unique_bodega_codigo(db, valores["codigo"])

    if es_admin(usuario):
        if valores.get("bodeguero_id") is not None:
            validate_bodeguero(db, valores["bodeguero_id"])
    else:
        valores["bodeguero_id"] = usuario.id  # el bodeguero siempre queda como dueño de lo que crea

    bodega = Bodega(**valores, creado_por=usuario.id, actualizado_por=usuario.id)
    db.add(bodega)
    db.commit()
    db.refresh(bodega)
    return bodega


def actualizar(db: Session, bodega_id: int, datos: BodegaUpdate, usuario: Usuario) -> Bodega:
    """Actualiza solo los campos enviados (los que lleguen en null se ignoran)
    y registra quién hizo el cambio. Ningún dato puede quedar vacío (lo valida el schema)."""
    bodega = get_bodega_or_404(db, bodega_id, usuario)
    cambios = datos.model_dump(exclude_none=True)  # null = no se cambia

    # Solo el admin puede cambiar el dueño; si lo envía un bodeguero, se ignora
    if not es_admin(usuario):
        cambios.pop("bodeguero_id", None)
    elif "bodeguero_id" in cambios:
        validate_bodeguero(db, cambios["bodeguero_id"])

    if "nombre" in cambios:
        validate_unique_bodega_name(db, cambios["nombre"], excluir_id=bodega_id)

    if cambios.get("codigo"):
        cambios["codigo"] = cambios["codigo"].upper()  # el código siempre se guarda en mayúsculas
        validate_unique_bodega_codigo(db, cambios["codigo"], excluir_id=bodega_id)

    for campo, valor in cambios.items():
        setattr(bodega, campo, valor)
    bodega.actualizado_por = usuario.id  # actualizado_en lo actualiza el mixin (onupdate)

    db.commit()
    db.refresh(bodega)
    return bodega


def eliminar(db: Session, bodega_id: int, usuario: Usuario) -> None:
    """Elimina una bodega (el bodeguero solo las suyas), si no tiene facturas ni tipos."""
    bodega = get_bodega_or_404(db, bodega_id, usuario)
    validate_se_puede_eliminar(db, bodega_id)
    db.delete(bodega)
    db.commit()
