# Lógica de cada endpoint de Auth. El router solo recibe la petición y llama a estas funciones.
from sqlalchemy.orm import Session, joinedload

from app.core.jwt import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
)
from app.modulos.auth.helpers import usuario_salida, validar_credenciales
from app.modulos.auth.schemas import (
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    RefreshResponse,
    UserOut,
)
from app.modulos.auth import errors
from app.modulos.empresas.helpers import validate_empresa_activa
from app.modulos.usuarios.models import Usuario


def login(datos: LoginRequest, db: Session) -> LoginResponse:
    """Valida correo y contraseña y devuelve tokens JWT con los datos del usuario."""
    usuario = validar_credenciales(db, datos.correo, datos.contrasena)
    access = create_access_token(usuario.id, usuario.rol.nombre)
    refresh = create_refresh_token(usuario.id)
    return LoginResponse(access_token=access, refresh_token=refresh, user=usuario_salida(usuario))


def login_docs(correo: str, contrasena: str, db: Session) -> dict:
    """Login del botón Authorize de /docs. Mismas reglas que POST /login, pero responde
    en el formato OAuth2 que espera Swagger: {"access_token", "token_type"}."""
    usuario = validar_credenciales(db, correo, contrasena)
    return {"access_token": create_access_token(usuario.id, usuario.rol.nombre), "token_type": "bearer"}


def refresh(datos: RefreshRequest, db: Session) -> RefreshResponse:
    """Valida el refresh_token y devuelve un access_token nuevo + un refresh_token nuevo (rotación)."""
    claims = decode_refresh_token(datos.refresh_token)
    if claims is None:
        raise errors.refresh_invalido()

    # Buscar el usuario en la BD (puede haberse desactivado desde que se emitió el refresh)
    try:
        user_id = int(claims.get("sub"))
    except (TypeError, ValueError):
        raise errors.refresh_invalido()

    usuario = (
        db.query(Usuario)
        .options(joinedload(Usuario.rol))
        .filter(Usuario.id == user_id)
        .first()
    )
    if usuario is None or not usuario.estado:
        raise errors.refresh_invalido()
    validate_empresa_activa(usuario)  # 403 si su empresa dejó de estar activa

    # Emitir tokens nuevos (rotación: el refresh anterior queda obsoleto)
    new_access = create_access_token(usuario.id, usuario.rol.nombre)
    new_refresh = create_refresh_token(usuario.id)
    return RefreshResponse(access_token=new_access, refresh_token=new_refresh)


def me(usuario: Usuario) -> UserOut:
    """Devuelve los datos del usuario dueño del token (sirve para recuperar la sesión)."""
    return usuario_salida(usuario)


def solo_admin(usuario: Usuario) -> dict:
    """Endpoint de prueba: solo accesible para el rol admin."""
    return {"mensaje": "Acceso de administrador"}
