# Validaciones del módulo Roles (lanzan el error HTTP que corresponde)
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.modulos.roles import queries
from app.modulos.roles.models import Rol


def get_rol_or_404(db: Session, rol_id: int) -> Rol:
    """Devuelve el rol o lanza 404 si no existe."""
    rol = queries.obtener(db, rol_id)
    if rol is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rol no encontrado")
    return rol


def validate_unique_rol_name(db: Session, nombre: str, excluir_id: int | None = None) -> None:
    """Lanza 400 si ya existe otro rol con ese nombre (sin distinguir mayúsculas)."""
    if queries.existe_nombre(db, nombre, excluir_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ya existe un rol con ese nombre",
        )
