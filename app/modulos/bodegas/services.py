# Lógica de cada endpoint de Bodegas. El router solo recibe la petición y llama a estas funciones.
# Alcance: admin todas; empresa las de su empresa; los demás solo las que les pertenecen (ver core/alcance.py).
from sqlalchemy.orm import Session

from app.core.alcance import Alcance, alcance_de
from app.modulos.bodegas import errors, queries
from app.modulos.bodegas.helpers import (get_bodega_or_404, validate_bodeguero, validate_estado_segun_empresa, validate_se_puede_eliminar,
                                         validate_unique_bodega_codigo, validate_unique_bodega_name)
from app.modulos.bodegas.models import Bodega
from app.modulos.bodegas.schemas import BodegaCreate, BodegaEstadoUpdate, BodegaOut, BodegaPaginado, BodegaUpdate
from app.modulos.usuarios.models import Usuario


def listar(db: Session, alcance: Alcance, q: str | None, estado: bool | None, bodeguero_id: int | None,
           page: int, limit: int) -> BodegaPaginado:
    """Lista las bodegas con búsqueda, filtros y paginación. El bodeguero solo ve las suyas."""
    if not alcance.ve_toda_la_empresa:
        bodeguero_id = alcance.usuario.id  # el bodeguero siempre ve solo sus bodegas

    total, bodegas = queries.listar(db, alcance, q=q, estado=estado, bodeguero_id=bodeguero_id, page=page, limit=limit)
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
    """Crea una bodega nueva, define su empresa y su dueño, y registra quién la creó."""
    alcance = alcance_de(usuario)
    empresa_id = alcance.empresa_para_crear(db, datos.empresa_id)  # admin: la del body; los demás: la del token
    validate_unique_bodega_name(db, datos.nombre)

    valores = datos.model_dump()
    valores["codigo"] = valores["codigo"].upper()  # el código siempre se guarda en mayúsculas
    validate_unique_bodega_codigo(db, valores["codigo"])

    valores["empresa_id"] = empresa_id  # nunca el del body sin validar
    if not alcance.ve_toda_la_empresa:
        valores["bodeguero_id"] = usuario.id  # el bodeguero siempre queda como dueño de lo que crea
    elif valores.get("bodeguero_id") is not None:
        bodeguero = validate_bodeguero(db, valores["bodeguero_id"], alcance)
        if bodeguero.empresa_id != empresa_id:
            raise errors.bodeguero_de_otra_empresa()

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
    validate_estado_segun_empresa(bodega, cambios)

    # Solo el admin o la empresa pueden cambiar el dueño; si lo envía un bodeguero, se ignora
    alcance = alcance_de(usuario)
    if not alcance.ve_toda_la_empresa:
        cambios.pop("bodeguero_id", None)
    elif "bodeguero_id" in cambios:
        bodeguero = validate_bodeguero(db, cambios["bodeguero_id"], alcance)
        if bodeguero.empresa_id != bodega.empresa_id:
            raise errors.bodeguero_de_otra_empresa()

    # Desactivarla la deja sin bodeguero y pasa sus tipos a generales de la empresa (no se borran ni se desactivan)
    if cambios.get("estado") is False:
        cambios["bodeguero_id"] = None
        queries.soltar_tipos(db, bodega_id)

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


def cambiar_estado(db: Session, bodega_id: int, datos: BodegaEstadoUpdate, usuario: Usuario) -> Bodega:
    """Activa o desactiva la bodega, con el mismo alcance que al editarla (la empresa, solo las suyas)."""
    return actualizar(db, bodega_id, BodegaUpdate(estado=datos.estado), usuario)


def eliminar(db: Session, bodega_id: int, usuario: Usuario) -> None:
    """Elimina una bodega (el bodeguero solo las suyas), si no tiene facturas. Sus tipos pasan a generales de la empresa
    y su bodeguero queda sin esta bodega; ninguno se borra ni se desactiva."""
    bodega = get_bodega_or_404(db, bodega_id, usuario)
    validate_se_puede_eliminar(db, bodega_id)
    queries.soltar_tipos(db, bodega_id)
    db.delete(bodega)
    db.commit()
