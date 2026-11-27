# Dependencias compartidas: obtener el usuario actual a partir del token
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session, joinedload

from app.config.database import get_db
from app.modulos.empresas.helpers import validate_empresa_activa
from app.modulos.usuarios.models import Usuario
from app.core.jwt import decode_access_token
from app.core.permisos import NOMBRES as NOMBRES_PERMISOS

# Lee el token del header "Authorization: Bearer <token>".
# tokenUrl es el login que usa el botón Authorize de /docs (correo y contraseña, sin copiar el token a mano).
# auto_error=False: si falta el header no responde solo; lo manejamos nosotros para responder 401.
oauth2 = OAuth2PasswordBearer(
    tokenUrl="/login/docs",
    auto_error=False,
    description="En **username** escribe tu **correo** y en **password** tu contraseña. "
                "Los campos client_id y client_secret se dejan vacíos.",
)


def _no_autorizado(mensaje: str) -> HTTPException:
    """Crea un error 401 con el header estándar WWW-Authenticate: Bearer."""
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=mensaje,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    token: str | None = Depends(oauth2),
    db: Session = Depends(get_db),
) -> Usuario:
    """Valida el token del header Authorization y devuelve el usuario con su rol.
    Responde 403 si el usuario pertenece a una empresa que no está activa, aunque el token sea válido."""
    # Sin header Authorization
    if token is None:
        raise _no_autorizado("No ha iniciado sesión")

    # Token vencido, alterado o mal formado
    claims = decode_access_token(token)
    if claims is None:
        raise _no_autorizado("Token inválido o vencido")

    # "sub" viene como texto; si no es un número, el token no es válido
    try:
        user_id = int(claims.get("sub"))
    except (TypeError, ValueError):
        raise _no_autorizado("Token inválido o vencido")

    # Busca el usuario y carga su rol en la misma consulta
    usuario = (
        db.query(Usuario)
        .options(joinedload(Usuario.rol), joinedload(Usuario.empresa))
        .filter(Usuario.id == user_id)
        .first()
    )

    # El usuario del token ya no existe en la BD o fue desactivado. Si lo desactivó la suspensión de su empresa,
    # responde el 403 de la empresa, como antes de que existiera la cascada
    if usuario is None or not (usuario.estado or usuario.desactivado_por_empresa):
        raise _no_autorizado("Token inválido o vencido")

    validate_empresa_activa(usuario)
    if not usuario.estado:
        raise _no_autorizado("Token inválido o vencido")
    return usuario


def require_roles(*roles_permitidos: str):
    """Dependencia que solo deja pasar a usuarios con alguno de los roles indicados.
    Uso: Depends(require_roles("admin", "bodeguero"))"""

    def verificar(usuario: Usuario = Depends(get_current_user)) -> Usuario:
        # Si no hay sesión, get_current_user ya respondió 401 antes de llegar aquí
        if usuario.rol.nombre not in roles_permitidos:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tiene permiso para esta acción",
            )
        return usuario

    return verificar


def prohibir_roles(*roles_prohibidos: str):
    """Dependencia que responde 403 a los roles indicados, AUNQUE tengan el permiso asignado.
    Va en `dependencies=[...]` del router o del endpoint, además de su require_permiso."""

    def verificar(usuario: Usuario = Depends(get_current_user)) -> None:
        if usuario.rol.nombre in roles_prohibidos:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tiene permiso para esta acción",
            )

    return verificar


# Lo que el rol empresa nunca puede hacer: gestionar permisos y roles, aceptar o rechazar facturas y todo /empresas
no_empresa = prohibir_roles("empresa")


def require_permiso(nombre: str):
    """Dependencia que solo deja pasar a quien tenga el permiso indicado (guardado en usuario_permisos).
    - El rol `admin` siempre pasa (acceso total, para que nadie se quede sin poder administrar).
    - Los permisos se leen de la base de datos en CADA petición: un cambio aplica de inmediato, sin renovar el token.
    - Un permiso desactivado (estado = false) no cuenta.
    Uso: Depends(require_permiso("tipos_create"))"""
    if nombre not in NOMBRES_PERMISOS:
        raise ValueError(f"Permiso desconocido: {nombre}")  # evita errores de tipeo al programar

    def verificar(usuario: Usuario = Depends(get_current_user)) -> Usuario:
        if usuario.rol.nombre == "admin":
            return usuario
        if not any(p.nombre == nombre and p.estado for p in usuario.permisos):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tiene permiso para esta acción",
            )
        return usuario

    return verificar
