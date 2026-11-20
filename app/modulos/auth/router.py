# Endpoints de autenticación (login y usuario de la sesión).
# Aquí solo están las rutas y su documentación. La lógica está en services.py, las validaciones
# en helpers.py, las consultas en queries.py y los errores (mensajes y ejemplos /docs) en errors.py.
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.modulos.usuarios.models import Usuario
from app.modulos.auth.schemas import LoginRequest, LoginResponse, UserOut
from app.core.deps import get_current_user, require_roles
from app.core.docs import ERROR_401
from app.modulos.auth import services
from app.modulos.auth.errors import DOC_401_LOGIN, DOC_422_LOGIN

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
        401: DOC_401_LOGIN,
        422: DOC_422_LOGIN,
    },
)
def login(datos: LoginRequest, db: Session = Depends(get_db)):
    """Valida correo y contraseña y devuelve un token JWT con los datos del usuario."""
    return services.login(datos, db)


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
    return services.me(usuario)


# TEMPORAL: borrar cuando haya CRUDs reales
@router.get("/solo-admin")
def solo_admin(usuario: Usuario = Depends(require_roles("admin"))):
    """Endpoint de prueba: solo accesible para el rol admin."""
    return services.solo_admin(usuario)
