# Endpoints de autenticación (login, refresh y usuario de la sesión).
# Aquí solo están las rutas y su documentación. La lógica está en services.py, las validaciones
# en helpers.py, las consultas en queries.py y los errores (mensajes y ejemplos /docs) en errors.py.
from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.modulos.usuarios.models import Usuario
from app.modulos.auth.schemas import LoginRequest, LoginResponse, RefreshRequest, RefreshResponse, UserOut
from app.core.deps import get_current_user, require_roles
from app.core.docs import ERROR_401
from app.modulos.auth import services
from app.modulos.auth.errors import DOC_401_LOGIN, DOC_401_REFRESH, DOC_403_EMPRESA, DOC_422_LOGIN, DOC_422_REFRESH

router = APIRouter(tags=["Auth"])


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="Iniciar sesión",
    description="""
Valida el correo **o el número de documento** y la contraseña, y devuelve un token JWT junto con los datos del usuario.

**Quién puede usarlo:** cualquiera. Es público y no requiere token.

**Cuerpo:**
- `correo` (**obligatorio**, o `identificador`): correo **o número de documento** del usuario. Si tiene `@` se busca por
  correo; si no, por número de documento, sin distinguir mayúsculas. Quien no tiene documento registrado entra con su correo.
- `identificador` (opcional): lo mismo que `correo`, con un nombre más claro. Si llegan los dos, se usa este.
- `contrasena` (**obligatorio**): contraseña del usuario.

**Reglas:**
- Si el correo o el documento no existe **o** la contraseña es incorrecta, responde el **mismo** 401
  (`Correo o contraseña incorrectos`), para no revelar cuál falló.
- Si no llega ni `correo` ni `identificador`: 422 `correo: es obligatorio`.
- Si las credenciales son correctas pero su empresa está pendiente, rechazada o suspendida, responde **403** con el motivo.
- El `access_token` vence a los **60 minutos**. Se puede renovar con `POST /refresh` sin pedir contraseña.
- El `refresh_token` vence a los **7 días** (configurable). Al usarlo se rota: se recibe uno nuevo.
- La respuesta nunca incluye la contraseña ni su hash.

**Cómo usar el token:** se envía en el header `Authorization: Bearer <access_token>`.
En esta página no hace falta copiarlo: pulsa **Authorize**, escribe tu correo o tu documento en **username** y tu contraseña
en **password**, y pulsa **Authorize** otra vez.

**Devuelve:** `access_token`, `refresh_token`, `token_type` (`bearer`) y `user` con `id`, `nombre`, `correo`, `rol` (como texto), `empresa` (`{id, razon_social, estado}` o `null`) y `permisos`.
""",
    response_description="Token JWT y datos del usuario",
    responses={
        401: DOC_401_LOGIN,
        403: DOC_403_EMPRESA,
        422: DOC_422_LOGIN,
    },
)
def login(datos: LoginRequest, db: Session = Depends(get_db)):
    """Valida correo y contraseña y devuelve un token JWT con los datos del usuario."""
    return services.login(datos, db)


# Login que usa el botón Authorize de /docs (no aparece en la lista de endpoints).
# Swagger envía un formulario OAuth2 con "username" y "password": en username va el correo.
# El frontend sigue usando POST /login con JSON.
@router.post("/login/docs", include_in_schema=False)
def login_docs(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """Inicia sesión desde /docs con correo y contraseña."""
    return services.login_docs(form.username, form.password, db)


@router.post(
    "/refresh",
    response_model=RefreshResponse,
    summary="Renovar access token",
    description="""
Recibe un `refresh_token` válido y devuelve un **nuevo** `access_token` y un **nuevo** `refresh_token` (rotación)
sin pedir correo ni contraseña.

**Quién puede usarlo:** cualquiera que tenga un refresh_token válido. Es público (no requiere `Authorization`).

**Cuerpo:**
- `refresh_token` (**obligatorio**): el refresh_token que se recibió en `POST /login` o en un `/refresh` anterior.

**Reglas:**
- Si el refresh_token está vencido, alterado o no es de tipo refresh, responde **401**.
- Si el usuario fue desactivado después del login, responde **401**.
- El refresh_token anterior queda obsoleto (rotación): usar siempre el nuevo.
- El access_token nuevo vence a los **60 minutos**; el refresh_token nuevo a los **7 días** (configurable).

**Devuelve:** `access_token`, `refresh_token` y `token_type` (`bearer`).
""",
    response_description="Nuevos tokens de acceso y refresco",
    responses={
        401: DOC_401_REFRESH,
        403: DOC_403_EMPRESA,
        422: DOC_422_REFRESH,
    },
)
def refresh(datos: RefreshRequest, db: Session = Depends(get_db)):
    """Renueva el access_token usando un refresh_token válido (con rotación)."""
    return services.refresh(datos, db)


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

**Devuelve:** `id`, `nombre`, `correo`, `rol` (como texto), `empresa` (`{id, razon_social, estado}` o `null`)
y `permisos` (`[{id, nombre}]`, sus permisos efectivos).
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
