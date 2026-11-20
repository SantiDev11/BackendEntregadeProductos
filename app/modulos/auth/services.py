# Lógica de cada endpoint de Auth. El router solo recibe la petición y llama a estas funciones.
from sqlalchemy.orm import Session

from app.core.jwt import create_access_token
from app.modulos.auth.helpers import usuario_salida, validar_credenciales
from app.modulos.auth.schemas import LoginRequest, LoginResponse, UserOut
from app.modulos.usuarios.models import Usuario


def login(datos: LoginRequest, db: Session) -> LoginResponse:
    """Valida correo y contraseña y devuelve un token JWT con los datos del usuario."""
    usuario = validar_credenciales(db, datos.correo, datos.contrasena)
    token = create_access_token(usuario.id, usuario.rol.nombre)
    return LoginResponse(access_token=token, user=usuario_salida(usuario))


def me(usuario: Usuario) -> UserOut:
    """Devuelve los datos del usuario dueño del token (sirve para recuperar la sesión)."""
    return usuario_salida(usuario)


def solo_admin(usuario: Usuario) -> dict:
    """Endpoint de prueba: solo accesible para el rol admin."""
    return {"mensaje": "Acceso de administrador"}
