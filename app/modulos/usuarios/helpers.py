# Validaciones del módulo Usuarios. Si algo no se cumple, lanzan el error de errors.py.
from sqlalchemy.orm import Session

from app.modulos.comun.validadores import error_documento
from app.modulos.permisos.models import Permiso
from app.modulos.roles.models import Rol
from app.modulos.usuarios import errors, queries
from app.modulos.usuarios.models import Usuario


def get_usuario_or_404(db: Session, usuario_id: int) -> Usuario:
    """Devuelve el usuario o lanza 404 si no existe."""
    usuario = queries.obtener(db, usuario_id)
    if usuario is None:
        raise errors.usuario_no_encontrado()
    return usuario


def validate_unique_usuario_email(db: Session, correo: str, excluir_id: int | None = None) -> None:
    """Lanza 400 si ya existe otro usuario con ese correo (sin distinguir mayúsculas)."""
    if queries.existe_correo(db, correo, excluir_id):
        raise errors.correo_duplicado()


def validate_rol_exists(db: Session, rol_id: int) -> Rol:
    """Lanza 400 si el rol indicado no existe; si existe, lo devuelve."""
    rol = queries.obtener_rol(db, rol_id)
    if rol is None:
        raise errors.rol_no_existe()
    return rol


def get_permiso_or_404(db: Session, permiso_id: int) -> Permiso:
    """Devuelve el permiso o lanza 404 si no existe."""
    permiso = queries.obtener_permiso(db, permiso_id)
    if permiso is None:
        raise errors.permiso_no_encontrado()
    return permiso


def validate_unique_usuario_documento(db: Session, numero_documento: str, excluir_id: int | None = None) -> None:
    """Lanza 400 si ya existe otro usuario con ese número de documento."""
    if queries.existe_documento(db, numero_documento, excluir_id):
        raise errors.documento_duplicado()


def validate_documento(tipo_documento: str | None, numero_documento: str | None) -> None:
    """Lanza 422 si el número no corresponde al tipo (solo números; con PA, letras y números)."""
    mensaje = error_documento(tipo_documento, numero_documento)
    if mensaje:
        raise errors.documento_invalido(mensaje)


def vacios_a_none(valores: dict) -> dict:
    """Convierte "" en None para guardar NULL (evita choques en los campos únicos como numero_documento)."""
    return {campo: (None if valor == "" else valor) for campo, valor in valores.items()}
