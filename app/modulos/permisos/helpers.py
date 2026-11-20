# Validaciones del módulo Permisos (lanzan el error HTTP que corresponde)
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.modulos.permisos import queries
from app.modulos.permisos.models import Permiso


def get_permiso_or_404(db: Session, permiso_id: int) -> Permiso:
    """Devuelve el permiso o lanza 404 si no existe."""
    permiso = queries.obtener(db, permiso_id)
    if permiso is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Permiso no encontrado")
    return permiso


def validate_unique_permiso_name(db: Session, nombre: str, excluir_id: int | None = None) -> None:
    """Lanza 400 si ya existe otro permiso con ese nombre (sin distinguir mayúsculas)."""
    if queries.existe_nombre(db, nombre, excluir_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ya existe un permiso con ese nombre",
        )
