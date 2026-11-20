# Validaciones y reglas del módulo Bodegas (lanzan el error HTTP que corresponde)
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.modulos.bodegas import queries
from app.modulos.bodegas.models import Bodega
from app.modulos.usuarios.models import Usuario

MSG_CODIGO_DUPLICADO = "Ya existe una bodega con ese código"
MSG_BODEGUERO_INVALIDO = "El bodeguero indicado no existe o no tiene rol bodeguero"


def es_admin(usuario: Usuario) -> bool:
    return usuario.rol.nombre == "admin"


def get_bodega_or_404(db: Session, bodega_id: int, usuario: Usuario) -> Bodega:
    """Devuelve la bodega o lanza 404 si no existe o si no le pertenece al usuario (salvo admin)."""
    bodega = queries.obtener(db, bodega_id)
    if bodega is None or (not es_admin(usuario) and bodega.bodeguero_id != usuario.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bodega no encontrada")
    return bodega


def validate_unique_bodega_name(db: Session, nombre: str, excluir_id: int | None = None) -> None:
    """Lanza 400 si ya existe otra bodega con ese nombre (sin distinguir mayúsculas)."""
    if queries.existe_nombre(db, nombre, excluir_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ya existe una bodega con ese nombre",
        )


def validate_unique_bodega_codigo(db: Session, codigo: str, excluir_id: int | None = None) -> None:
    """Lanza 400 si ya existe otra bodega con ese código (sin distinguir mayúsculas)."""
    if queries.existe_codigo(db, codigo, excluir_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=MSG_CODIGO_DUPLICADO)


def validate_bodeguero(db: Session, bodeguero_id: int) -> None:
    """Lanza 400 si el id no corresponde a un usuario con rol bodeguero."""
    if not queries.es_bodeguero(db, bodeguero_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=MSG_BODEGUERO_INVALIDO)
