# Validaciones y reglas del módulo Bodegas. Si algo no se cumple, lanzan el error de errors.py.
from sqlalchemy.orm import Session

from app.modulos.bodegas import errors, queries
from app.modulos.bodegas.models import Bodega
from app.modulos.usuarios.models import Usuario


def es_admin(usuario: Usuario) -> bool:
    return usuario.rol.nombre == "admin"


def get_bodega_or_404(db: Session, bodega_id: int, usuario: Usuario) -> Bodega:
    """Devuelve la bodega o lanza 404 si no existe o si no le pertenece al usuario (salvo admin)."""
    bodega = queries.obtener(db, bodega_id)
    if bodega is None or (not es_admin(usuario) and bodega.bodeguero_id != usuario.id):
        raise errors.bodega_no_encontrada()
    return bodega


def validate_unique_bodega_name(db: Session, nombre: str, excluir_id: int | None = None) -> None:
    """Lanza 400 si ya existe otra bodega con ese nombre (sin distinguir mayúsculas)."""
    if queries.existe_nombre(db, nombre, excluir_id):
        raise errors.nombre_duplicado()


def validate_unique_bodega_codigo(db: Session, codigo: str, excluir_id: int | None = None) -> None:
    """Lanza 400 si ya existe otra bodega con ese código (sin distinguir mayúsculas)."""
    if queries.existe_codigo(db, codigo, excluir_id):
        raise errors.codigo_duplicado()


def validate_bodeguero(db: Session, bodeguero_id: int) -> None:
    """Lanza 400 si el id no corresponde a un usuario con rol bodeguero."""
    if not queries.es_bodeguero(db, bodeguero_id):
        raise errors.bodeguero_invalido()


def validate_se_puede_eliminar(db: Session, bodega_id: int) -> None:
    """Lanza 400 si la bodega tiene facturas o tipos (evita el error 500 de clave foránea)."""
    if queries.tiene_facturas(db, bodega_id):
        raise errors.tiene_facturas()
    if queries.tiene_tipos(db, bodega_id):
        raise errors.tiene_tipos()  # primero hay que borrar o mover sus tipos
