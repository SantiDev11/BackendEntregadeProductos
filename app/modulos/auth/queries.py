# Consultas a la base de datos del módulo Auth
from sqlalchemy.orm import Session

from app.modulos.usuarios.models import Usuario


def buscar_usuario_para_login(db: Session, identificador: str) -> Usuario | None:
    """Usuario con ese correo (si tiene @) o con ese número de documento (si no), o None si no existe.
    Un documento nunca tiene @ (solo letras y números), así que no se confunden. Los dos son únicos y la base
    los compara sin distinguir mayúsculas."""
    if "@" in identificador:
        return db.query(Usuario).filter(Usuario.correo == identificador.lower()).first()
    return db.query(Usuario).filter(Usuario.numero_documento == identificador).first()
