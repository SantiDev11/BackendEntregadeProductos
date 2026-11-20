# Validaciones y ayudas del módulo Auth. Si algo no se cumple, lanzan el error de errors.py.
from sqlalchemy.orm import Session

from app.core.security import verify_password
from app.modulos.auth import errors, queries
from app.modulos.auth.schemas import UserOut
from app.modulos.roles.schemas import PermisoResumen
from app.modulos.usuarios.models import Usuario


def validar_credenciales(db: Session, correo: str, contrasena: str) -> Usuario:
    """Devuelve el usuario si el correo existe, la contraseña es correcta y está activo.
    Si falla cualquiera de los tres lanza el mismo 401, para no revelar cuál falló."""
    usuario = queries.buscar_usuario_por_correo(db, correo)
    if not usuario or not verify_password(contrasena, usuario.contrasena) or not usuario.estado:
        raise errors.credenciales_invalidas()
    return usuario


def usuario_salida(usuario: Usuario) -> UserOut:
    """Datos del usuario que se devuelven al frontend, con sus permisos (el rol va como texto)."""
    return UserOut(
        id=usuario.id,
        nombre=usuario.nombre,
        correo=usuario.correo,
        rol=usuario.rol.nombre,
        permisos=[PermisoResumen.model_validate(p) for p in usuario.permisos],
    )
