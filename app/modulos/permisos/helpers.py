# Validaciones del módulo Permisos. Si algo no se cumple, lanzan el error de errors.py.
from sqlalchemy.orm import Session

from app.modulos.permisos import errors, queries
from app.modulos.permisos.models import Permiso


def get_permiso_or_404(db: Session, permiso_id: int) -> Permiso:
    """Devuelve el permiso o lanza 404 si no existe."""
    permiso = queries.obtener(db, permiso_id)
    if permiso is None:
        raise errors.permiso_no_encontrado()
    return permiso


def validate_unique_permiso_name(db: Session, nombre: str, excluir_id: int | None = None) -> None:
    """Lanza 400 si ya existe otro permiso con ese nombre (sin distinguir mayúsculas)."""
    if queries.existe_nombre(db, nombre, excluir_id):
        raise errors.nombre_duplicado()
