# Endpoints de Empresas: solo el rol admin (cualquier otro recibe 403, aunque tenga permisos asignados).
# Aquí solo están las rutas y su documentación. La lógica está en services.py, las validaciones
# en helpers.py, las consultas en queries.py y los errores (mensajes y ejemplos /docs) en errors.py.
from fastapi import APIRouter, Depends, Path, Query, Response, status
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.deps import require_roles
from app.core.docs import ERROR_401
from app.modulos.empresas import services
from app.modulos.empresas.errors import (DOC_400_ACTUALIZAR, DOC_400_CREAR, DOC_400_ELIMINAR, DOC_400_ESTADO, DOC_403, DOC_404,
                                         DOC_422_ACTUALIZAR, DOC_422_CREAR, DOC_422_ESTADO, DOC_422_ID, DOC_422_LISTAR)
from app.modulos.empresas.schemas import EmpresaCreate, EmpresaEstadoUpdate, EmpresaOut, EmpresaPaginado, EmpresaUpdate
from app.modulos.usuarios.models import Usuario

solo_admin = require_roles("admin")

router = APIRouter(
    prefix="/empresas",
    tags=["Empresas"],
    dependencies=[Depends(solo_admin)],
)


# ===== CONSULTAS (GET) =====

@router.get(
    "",
    response_model=EmpresaPaginado,
    summary="Listar empresas",
    description="""
Devuelve las empresas en páginas, de la más reciente a la más antigua, con búsqueda y filtro por estado.

**Quién puede usarlo:** solo el rol `admin`. Requiere `Authorization: Bearer <token>`.

**Parámetros (todos opcionales):**
- `q`: busca en la razón social, el NIT o el correo (contiene, sin distinguir mayúsculas).
- `estado`: `pendiente`, `activa`, `rechazada` o `suspendida`. Si no se envía, devuelve todas.
- `page`: número de página, empieza en 1.
- `limit`: elementos por página, por defecto 10 y máximo 100.

**Devuelve:** `{"data": [...], "total": n, "page": p, "limit": l}`. Cada empresa trae sus totales de bodegueros, bodegas y facturas.
""",
    response_description="Página de empresas con el total que cumple los filtros",
    responses={401: ERROR_401, 403: DOC_403, 422: DOC_422_LISTAR},
)
def listar_empresas(
    q: str | None = Query(None, description="Texto a buscar en la razón social, el NIT o el correo."),
    estado: str | None = Query(None, description="Filtra por estado: pendiente, activa, rechazada o suspendida."),
    page: int = Query(1, ge=1, description="Número de página. Empieza en 1."),
    limit: int = Query(10, ge=1, le=100, description="Elementos por página. Por defecto 10, máximo 100."),
    db: Session = Depends(get_db),
):
    """Lista las empresas con búsqueda, filtro por estado y paginación."""
    return services.listar(db, q=q, estado=estado, page=page, limit=limit)


@router.get(
    "/{empresa_id}",
    response_model=EmpresaOut,
    summary="Obtener una empresa",
    description="""
Devuelve una empresa por su id, con sus totales de bodegueros, bodegas y facturas.

**Quién puede usarlo:** solo el rol `admin`. Requiere `Authorization: Bearer <token>`.

**Devuelve:** la empresa, o 404 si no existe.
""",
    response_description="La empresa encontrada",
    responses={401: ERROR_401, 403: DOC_403, 404: DOC_404, 422: DOC_422_ID},
)
def obtener_empresa(
    empresa_id: int = Path(description="Id de la empresa.", examples=[1]),
    db: Session = Depends(get_db),
):
    """Devuelve una empresa por su id."""
    return services.obtener(db, empresa_id)


# ===== CREAR (POST) =====

@router.post(
    "",
    response_model=EmpresaOut,
    status_code=status.HTTP_201_CREATED,
    summary="Crear una empresa con su usuario",
    description="""
Crea una empresa **ya activa** y su usuario con rol `empresa`, que puede iniciar sesión de inmediato.

**Quién puede usarlo:** solo el rol `admin`. Requiere `Authorization: Bearer <token>`.

**Cuerpo:** los mismos datos y reglas de `POST /register` con `tipo: "empresa"`, **todos obligatorios**: `razon_social`, `nit`,
`telefono`, `direccion`, `representante`, `correo` y `contrasena`.

**Reglas:**
- Todo va en una transacción: o se crean la empresa y su usuario, o no queda nada.
- El usuario entra con el `correo` y la `contrasena` enviados, y su nombre es el del `representante`.
- El `correo` es único entre todos los usuarios y el `nit` entre las empresas, sin contar el dígito de verificación (400).
- El estado, el rol y los permisos los pone el servidor: si llegan en el cuerpo, se ignoran.

**Devuelve:** 201 con la empresa. La contraseña nunca se devuelve.
""",
    response_description="La empresa creada",
    responses={400: DOC_400_CREAR, 401: ERROR_401, 403: DOC_403, 422: DOC_422_CREAR},
)
def crear_empresa(
    datos: EmpresaCreate,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(solo_admin),
):
    """Crea una empresa activa con su usuario."""
    return services.crear(db, datos, admin)


# ===== EDITAR (PUT) =====

@router.put(
    "/{empresa_id}",
    response_model=EmpresaOut,
    summary="Editar una empresa",
    description="""
Actualiza los datos de una empresa, en cualquier estado. **Solo cambia los campos que se envían.**

**Quién puede usarlo:** solo el rol `admin`. Requiere `Authorization: Bearer <token>`.

**Cuerpo (todos opcionales):** `razon_social`, `nit`, `telefono`, `direccion`, `representante` y `correo`.

**Reglas:**
- Un campo que no se envía, o que llega en `null`, no se cambia. Ninguno se puede borrar: `""` da 422.
- El `nit` no puede tenerlo **otra** empresa (400).
- El `correo` es el de contacto: **no** cambia el correo con el que entra su usuario. Tampoco cambia su nombre.
- El estado se cambia con `PATCH /empresas/{id}/estado`: si llega en el cuerpo, se ignora.

**Devuelve:** la empresa actualizada.
""",
    response_description="La empresa con los cambios aplicados",
    responses={400: DOC_400_ACTUALIZAR, 401: ERROR_401, 403: DOC_403, 404: DOC_404, 422: DOC_422_ACTUALIZAR},
)
def actualizar_empresa(
    datos: EmpresaUpdate,
    empresa_id: int = Path(description="Id de la empresa a editar.", examples=[1]),
    db: Session = Depends(get_db),
):
    """Actualiza solo los campos enviados."""
    return services.actualizar(db, empresa_id, datos)


# ===== CAMBIAR ESTADO (PATCH) =====

@router.patch(
    "/{empresa_id}/estado",
    response_model=EmpresaOut,
    summary="Aprobar, rechazar, suspender o reactivar una empresa",
    description="""
Cambia el estado de una empresa.

**Quién puede usarlo:** solo el rol `admin`. Requiere `Authorization: Bearer <token>`.

**Cuerpo:**
- `estado` (**obligatorio**): `activa`, `rechazada` o `suspendida`.
- `motivo_rechazo`: **obligatorio solo al rechazar**, de 10 a 255 caracteres. Con otro estado se ignora.

**Cambios permitidos** (cualquier otro da 400):
- `pendiente` → `activa` o `rechazada`
- `activa` → `suspendida`
- `suspendida` → `activa`
- `rechazada` → `activa`

**Reglas:**
- Al pasar a `activa` se borra el motivo de rechazo.
- Mientras no esté `activa`, **ninguno de sus usuarios** puede entrar (403), aunque tenga un token vigente.
- Sus bodegas y facturas no se borran.

**Devuelve:** la empresa con su nuevo estado.
""",
    response_description="La empresa con su nuevo estado",
    responses={400: DOC_400_ESTADO, 401: ERROR_401, 403: DOC_403, 404: DOC_404, 422: DOC_422_ESTADO},
)
def cambiar_estado_empresa(
    datos: EmpresaEstadoUpdate,
    empresa_id: int = Path(description="Id de la empresa.", examples=[1]),
    db: Session = Depends(get_db),
):
    """Aprueba, rechaza, suspende o reactiva una empresa."""
    return services.cambiar_estado(db, empresa_id, datos)


# ===== ELIMINAR (DELETE) =====

@router.delete(
    "/{empresa_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar una empresa sin facturas",
    description="""
Elimina una empresa de forma **definitiva**, junto con **todos sus usuarios** (el de la empresa, sus bodegueros y los de
otros roles), **sus bodegas** y **sus tipos**. No se puede deshacer.

**Quién puede usarlo:** solo el rol `admin`. Requiere `Authorization: Bearer <token>`.

**Reglas:**
- **Si tiene facturas, no se borra nada** y responde 400: las facturas son también de los clientes y quedan como respaldo.
  Cuentan las de la empresa, las de sus bodegas, las que crearon sus usuarios y las que tienen sus tipos en el detalle.
- También responde 400 si uno de sus usuarios está a cargo de una bodega de **otra** empresa: las ajenas no se borran.
- Los usuarios borrados ya no pueden iniciar sesión y sus tokens dejan de funcionar. Sus correos, documentos y el NIT quedan libres.
- Es todo o nada: si algo falla, no se borra nada.
- Para quitarle el acceso sin borrarla, usa `PATCH /empresas/{id}/estado` con `{"estado": "suspendida"}`.

**Devuelve:** 204 **sin cuerpo**.
""",
    response_description="Empresa eliminada. La respuesta no tiene cuerpo",
    responses={400: DOC_400_ELIMINAR, 401: ERROR_401, 403: DOC_403, 404: DOC_404, 422: DOC_422_ID},
)
def eliminar_empresa(
    empresa_id: int = Path(description="Id de la empresa a eliminar.", examples=[1]),
    db: Session = Depends(get_db),
):
    """Elimina una empresa sin facturas, con sus usuarios, bodegas y tipos. Responde 204 sin cuerpo."""
    services.eliminar(db, empresa_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
