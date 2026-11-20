# Validaciones del módulo Usuarios (lanzan el error HTTP que corresponde)
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.modulos.permisos.models import Permiso
from app.modulos.roles.models import Rol
from app.modulos.usuarios import queries
from app.modulos.usuarios.models import Usuario

MSG_CORREO_DUPLICADO = "Ya existe un usuario con ese correo"
MSG_ROL_NO_EXISTE = "El rol indicado no existe"
MSG_DOCUMENTO_DUPLICADO = "Ya existe un usuario con ese documento"


def get_usuario_or_404(db: Session, usuario_id: int) -> Usuario:
    """Devuelve el usuario o lanza 404 si no existe."""
    usuario = queries.obtener(db, usuario_id)
    if usuario is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
    return usuario


def validate_unique_usuario_email(db: Session, correo: str, excluir_id: int | None = None) -> None:
    """Lanza 400 si ya existe otro usuario con ese correo (sin distinguir mayúsculas)."""
    if queries.existe_correo(db, correo, excluir_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=MSG_CORREO_DUPLICADO)


def validate_rol_exists(db: Session, rol_id: int) -> Rol:
    """Lanza 400 si el rol indicado no existe; si existe, lo devuelve."""
    rol = queries.obtener_rol(db, rol_id)
    if rol is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=MSG_ROL_NO_EXISTE)
    return rol


def get_permiso_or_404(db: Session, permiso_id: int) -> Permiso:
    """Devuelve el permiso o lanza 404 si no existe."""
    permiso = queries.obtener_permiso(db, permiso_id)
    if permiso is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Permiso no encontrado")
    return permiso


def validate_unique_usuario_documento(db: Session, numero_documento: str, excluir_id: int | None = None) -> None:
    """Lanza 400 si ya existe otro usuario con ese número de documento."""
    if queries.existe_documento(db, numero_documento, excluir_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=MSG_DOCUMENTO_DUPLICADO)


def vacios_a_none(valores: dict) -> dict:
    """Convierte "" en None para guardar NULL (evita choques en los campos únicos como numero_documento)."""
    return {campo: (None if valor == "" else valor) for campo, valor in valores.items()}
