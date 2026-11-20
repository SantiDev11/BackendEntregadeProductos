# Consultas a la base de datos del módulo Auth
from sqlalchemy.orm import Session

from app.modulos.usuarios.models import Usuario


def buscar_usuario_por_correo(db: Session, correo: str) -> Usuario | None:
    """Usuario con ese correo, o None si no existe."""
    return db.query(Usuario).filter(Usuario.correo == correo).first()
