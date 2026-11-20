# Lógica de cada endpoint de Tipos. El router solo recibe la petición y llama a estas funciones.
from sqlalchemy.orm import Session

from app.modulos.tipos import queries
from app.modulos.tipos.helpers import (bodega_para_nuevo_tipo, bodegas_permitidas, es_admin, get_tipo_or_404,
                                       validate_bodega_existe, validate_se_puede_eliminar,
                                       validate_unique_tipo_name)
from app.modulos.tipos.models import Tipo
from app.modulos.tipos.schemas import TipoCreate, TipoUpdate, TipoOut, TipoPaginado
from app.modulos.usuarios.models import Usuario


def listar_tipos(q: str | None, estado: bool | None, bodega_id: int | None, page: int, limit: int, db: Session,
                 usuario: Usuario):
    """Lista los tipos con búsqueda, filtros y paginación. Quien no es admin solo ve los de sus bodegas."""
    total, tipos = queries.listar(db, q=q, estado=estado, bodega_id=bodega_id,
                                  bodegas_permitidas=bodegas_permitidas(db, usuario), page=page, limit=limit)

    return TipoPaginado(
        data=[TipoOut.model_validate(t) for t in tipos],
        total=total,
        page=page,
        limit=limit,
    )


def obtener_tipo(tipo_id: int, db: Session, usuario: Usuario):
    """Devuelve un tipo por su id (si es de una de las bodegas del usuario, o si es admin)."""
    return get_tipo_or_404(db, tipo_id, usuario)


def crear_tipo(datos: TipoCreate, db: Session, usuario: Usuario):
    """Crea un tipo en la bodega que corresponde y registra quién lo creó."""
    bodega_id = bodega_para_nuevo_tipo(db, usuario, datos.bodega_id)
    validate_unique_tipo_name(db, datos.nombre, bodega_id)

    valores = datos.model_dump()
    valores["bodega_id"] = bodega_id
    tipo = Tipo(**valores, creado_por=usuario.id, actualizado_por=usuario.id)
    db.add(tipo)
    db.commit()
    db.refresh(tipo)
    return tipo


def actualizar_tipo(datos: TipoUpdate, tipo_id: int, db: Session, usuario: Usuario):
    """Actualiza solo los campos enviados (los que lleguen en null se ignoran)
    y registra quién hizo el cambio."""
    tipo = get_tipo_or_404(db, tipo_id, usuario)
    cambios = datos.model_dump(exclude_none=True)

    # Solo el admin puede mover el tipo a otra bodega; si lo envía otro usuario, se ignora
    if not es_admin(usuario):
        cambios.pop("bodega_id", None)
    elif "bodega_id" in cambios:
        validate_bodega_existe(db, cambios["bodega_id"])

    # El nombre se valida contra la bodega en la que va a quedar el tipo
    if "nombre" in cambios or "bodega_id" in cambios:
        validate_unique_tipo_name(db, cambios.get("nombre", tipo.nombre),
                                  cambios.get("bodega_id", tipo.bodega_id), excluir_id=tipo_id)

    for campo, valor in cambios.items():
        setattr(tipo, campo, valor)
    tipo.actualizado_por = usuario.id  # actualizado_en lo actualiza el mixin (onupdate)

    db.commit()
    db.refresh(tipo)
    return tipo


def eliminar_tipo(tipo_id: int, db: Session, usuario: Usuario):
    """Elimina un tipo (si es de una de las bodegas del usuario, o si es admin). Responde 204 sin cuerpo."""
    tipo = get_tipo_or_404(db, tipo_id, usuario)

    validate_se_puede_eliminar(db, tipo_id)

    db.delete(tipo)
    db.commit()
