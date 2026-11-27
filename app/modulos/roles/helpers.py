# Validaciones del módulo Roles. Si algo no se cumple, lanzan el error de errors.py.
from sqlalchemy.orm import Session

from app.core.permisos import PLANTILLAS
from app.modulos.roles import errors, queries
from app.modulos.roles.models import Rol
from app.modulos.usuarios.models import Usuario


def get_rol_or_404(db: Session, rol_id: int) -> Rol:
    """Devuelve el rol o lanza 404 si no existe."""
    rol = queries.obtener(db, rol_id)
    if rol is None:
        raise errors.rol_no_encontrado()
    return rol


def validate_puede_renombrar(rol: Rol, nombre: str, usuario: Usuario) -> None:
    """Lanza 403 si quien no es admin intenta cambiarle el nombre a un rol base (admin, bodeguero, empresa, cliente).
    El acceso del admin depende del nombre: podría renombrarlo y llamar "admin" a su propio rol."""
    if rol.nombre in PLANTILLAS and nombre != rol.nombre and usuario.rol.nombre != "admin":
        raise errors.rol_base()


def validate_puede_desactivar(rol: Rol, estado: bool, usuario: Usuario) -> None:
    """Lanza 400 si se intenta desactivar el rol admin, o el propio rol de quien hace el cambio (se quedaría sin acceso).
    Los demás roles sí se pueden desactivar: dejan de asignarse y sus usuarios quedan inactivos hasta que se reactive."""
    if estado is False and rol.nombre == "admin":
        raise errors.admin_no_se_desactiva()
    if estado is False and usuario.rol_id == rol.id:
        raise errors.propio_rol()


def validate_unique_rol_name(db: Session, nombre: str, excluir_id: int | None = None) -> None:
    """Lanza 400 si ya existe otro rol con ese nombre (sin distinguir mayúsculas)."""
    if queries.existe_nombre(db, nombre, excluir_id):
        raise errors.nombre_duplicado()
