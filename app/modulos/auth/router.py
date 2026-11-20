# Endpoints de autenticación (login y usuario de la sesión)
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.modulos.auth import queries
from app.modulos.usuarios.models import Usuario
from app.modulos.auth.schemas import LoginRequest, LoginResponse, UserOut
from app.modulos.roles.schemas import PermisoResumen
from app.core.security import verify_password
from app.core.jwt import create_access_token
from app.core.deps import get_current_user, require_roles
from app.core.docs import ERROR_401, respuesta_error

router = APIRouter(tags=["Auth"])


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="Iniciar sesión",
    description="""
Valida el correo y la contraseña y devuelve un token JWT junto con los datos del usuario.

**Quién puede usarlo:** cualquiera. Es público y no requiere token.

**Cuerpo:**
- `correo` (**obligatorio**): correo del usuario, con formato válido.
- `contrasena` (**obligatorio**): contraseña del usuario.

**Reglas:**
- Si el correo no existe **o** la contraseña es incorrecta, responde el **mismo** 401, para no revelar cuál de los dos falló.
- El token vence a los **60 minutos**. Después hay que volver a iniciar sesión.
- La respuesta nunca incluye la contraseña ni su hash.

**Cómo usar el token:** se envía en el header `Authorization: Bearer <access_token>`.
En esta página, pulsa **Authorize** y pega solo el token, sin la palabra "Bearer".

**Devuelve:** `access_token`, `token_type` (`bearer`) y `user` con `id`, `nombre`, `correo`, `rol` (como texto) y `permisos`.
""",
    response_description="Token JWT y datos del usuario",
    responses={
        401: respuesta_error(
            "El correo no existe o la contraseña es incorrecta",
            credenciales_invalidas="Correo o contraseña incorrectos",
        ),
        422: respuesta_error(
            "El cuerpo no cumple las validaciones",
            campos_faltantes="correo: es obligatorio; contrasena: es obligatorio",
            correo_invalido="correo: formato de correo inválido",
            json_invalido="El cuerpo de la petición no es un JSON válido",
        ),
    },
)
def login(datos: LoginRequest, db: Session = Depends(get_db)):
    """Valida correo y contraseña y devuelve un token JWT con los datos del usuario."""
    usuario = queries.buscar_usuario_por_correo(db, datos.correo)

    # Mismo mensaje si el correo no existe, la contraseña es incorrecta o el usuario
    # está inactivo, para no revelar cuál de los tres falló
    if not usuario or not verify_password(datos.contrasena, usuario.contrasena) or not usuario.estado:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Correo o contraseña incorrectos",
        )

    token = create_access_token(usuario.id, usuario.rol.nombre)

    return LoginResponse(
        access_token=token,
        user=UserOut(
            id=usuario.id,
            nombre=usuario.nombre,
            correo=usuario.correo,
            rol=usuario.rol.nombre,  # el rol va como texto
            permisos=[PermisoResumen.model_validate(p) for p in usuario.permisos],
        ),
    )


@router.get(
    "/me",
    response_model=UserOut,
    summary="Usuario de la sesión actual",
    description="""
Devuelve los datos del usuario dueño del token.
Sirve para que el frontend recupere la sesión, por ejemplo al recargar la página.

**Quién puede usarlo:** cualquier usuario con sesión (`admin`, `bodeguero` o `cliente`).
Requiere `Authorization: Bearer <token>`.

**Parámetros:** ninguno. El usuario se toma del token.

**Devuelve:** `id`, `nombre`, `correo`, `rol` (como texto) y `permisos` (`[{id, nombre}]`, sus permisos efectivos).
Nunca incluye la contraseña.
""",
    response_description="Datos del usuario autenticado, con sus permisos",
    responses={401: ERROR_401},
)
def me(usuario: Usuario = Depends(get_current_user)):
    """Devuelve los datos del usuario dueño del token (sirve para recuperar la sesión)."""
    return UserOut(
        id=usuario.id,
        nombre=usuario.nombre,
        correo=usuario.correo,
        rol=usuario.rol.nombre,
        permisos=[PermisoResumen.model_validate(p) for p in usuario.permisos],
    )


# TEMPORAL: borrar cuando haya CRUDs reales
@router.get("/solo-admin")
def solo_admin(usuario: Usuario = Depends(require_roles("admin"))):
    """Endpoint de prueba: solo accesible para el rol admin."""
    return {"mensaje": "Acceso de administrador"}
