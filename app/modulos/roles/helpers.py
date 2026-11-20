# Validaciones del módulo Roles. Si algo no se cumple, lanzan el error de errors.py.
from sqlalchemy.orm import Session

from app.modulos.roles import errors, queries
from app.modulos.roles.models import Rol


def get_rol_or_404(db: Session, rol_id: int) -> Rol:
    """Devuelve el rol o lanza 404 si no existe."""
    rol = queries.obtener(db, rol_id)
    if rol is None:
        raise errors.rol_no_encontrado()
    return rol


def validate_unique_rol_name(db: Session, nombre: str, excluir_id: int | None = None) -> None:
    """Lanza 400 si ya existe otro rol con ese nombre (sin distinguir mayúsculas)."""
    if queries.existe_nombre(db, nombre, excluir_id):
        raise errors.nombre_duplicado()
