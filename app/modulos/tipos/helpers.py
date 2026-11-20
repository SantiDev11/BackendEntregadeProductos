# Validaciones y reglas del módulo Tipos (lanzan el error HTTP que corresponde).
# Cada tipo pertenece a una bodega: el admin maneja todos; cualquier otro usuario solo los de sus bodegas.
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.modulos.tipos import queries
from app.modulos.tipos.models import Tipo
from app.modulos.usuarios.models import Usuario

MSG_SIN_BODEGA = "No tiene una bodega asignada: no puede crear tipos"
MSG_VARIAS_BODEGAS = "Tiene varias bodegas: indique bodega_id con una de las suyas"
MSG_BODEGA_INVALIDA = "La bodega indicada no existe o no le pertenece"
MSG_TIPO_AJENO = "El tipo no pertenece a su bodega"


def es_admin(usuario: Usuario) -> bool:
    return usuario.rol.nombre == "admin"


def bodegas_permitidas(db: Session, usuario: Usuario) -> list[int] | None:
    """None si puede ver todas (admin); si no, los ids de sus bodegas."""
    return None if es_admin(usuario) else queries.ids_bodegas_del_usuario(db, usuario.id)


def get_tipo_or_404(db: Session, tipo_id: int, usuario: Usuario) -> Tipo:
    """Devuelve el tipo; 404 si no existe y 403 si es de una bodega que no es del usuario (salvo admin)."""
    tipo = queries.obtener(db, tipo_id)
    if tipo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tipo no encontrado")
    if not es_admin(usuario) and tipo.bodega_id not in queries.ids_bodegas_del_usuario(db, usuario.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=MSG_TIPO_AJENO)
    return tipo


def bodega_para_nuevo_tipo(db: Session, usuario: Usuario, bodega_id: int | None) -> int | None:
    """Decide a qué bodega va un tipo nuevo.
    - Admin: la que envía (debe existir) o ninguna si no la envía.
    - Otro usuario: su única bodega; si tiene varias, la que envía (debe ser suya); si no tiene, 400."""
    if es_admin(usuario):
        if bodega_id is not None and queries.obtener_bodega(db, bodega_id) is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=MSG_BODEGA_INVALIDA)
        return bodega_id

    propias = queries.ids_bodegas_del_usuario(db, usuario.id)
    if not propias:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=MSG_SIN_BODEGA)
    if len(propias) == 1:
        return propias[0]  # una sola bodega: se asigna sola, sin importar lo que venga en el cuerpo
    if bodega_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=MSG_VARIAS_BODEGAS)
    if bodega_id not in propias:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=MSG_BODEGA_INVALIDA)
    return bodega_id


def validate_bodega_existe(db: Session, bodega_id: int) -> None:
    """Lanza 400 si la bodega no existe (para cuando el admin mueve un tipo)."""
    if queries.obtener_bodega(db, bodega_id) is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=MSG_BODEGA_INVALIDA)


def validate_unique_tipo_name(db: Session, nombre: str, bodega_id: int | None, excluir_id: int | None = None) -> None:
    """Lanza 400 si ya existe otro tipo con ese nombre en la misma bodega (sin distinguir mayúsculas)."""
    if queries.existe_nombre(db, nombre, bodega_id, excluir_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ya existe un tipo con ese nombre en esta bodega",
        )
