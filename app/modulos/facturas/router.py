# Endpoints de Facturas (la orden ES la factura): borrador editable + acciones que la hacen avanzar de estado.
# Las consultas a la BD están en queries.py; cálculos, reglas y validaciones en helpers.py; el PDF en pdf.py.
from fastapi import APIRouter, Depends, Path, Query, Response, status
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.deps import get_current_user, require_permiso
from app.core.docs import ERROR_401
from app.modulos.facturas.schemas import (ClientePaginado, FacturaCreate, FacturaOut, FacturaPaginado, FacturaUpdate,
                                          FirmaIn, RechazoIn)
from app.modulos.usuarios.models import Usuario
from app.modulos.facturas import services
from app.modulos.facturas.errors import (DOC_404, DOC_422_ID, DOC_400_ESTADO, DOC_403_GESTION, DOC_403_CLIENTE,
                                         DOC_422_LISTAR_FACTURAS, DOC_422_LISTAR_CLIENTES_PARA_FACTURAR, DOC_400_CREAR,
                                         DOC_422_CREAR, DOC_400_ACTUALIZAR, DOC_422_ACTUALIZAR, DOC_422_ACEPTAR,
                                         DOC_422_RECHAZAR)

# Permiso que exige cada acción (los permisos se leen de la BD en cada petición; el rol admin siempre pasa)
puede_ver = require_permiso("facturas_view")
puede_crear = require_permiso("facturas_create")
puede_pdf = require_permiso("facturas_pdf")
puede_editar = require_permiso("facturas_edit")
puede_entregar = require_permiso("facturas_entregar")
puede_aceptar = require_permiso("facturas_aceptar")
puede_rechazar = require_permiso("facturas_rechazar")
puede_recibir = require_permiso("facturas_recibir")
puede_eliminar = require_permiso("facturas_delete")

# Todos los endpoints exigen sesión; cada uno exige además su permiso (ver arriba)
router = APIRouter(
    prefix="/facturas",
    tags=["Facturas"],
    dependencies=[Depends(get_current_user)],
)


# ===== CONSULTAS (GET) =====

@router.get(
    "",
    response_model=FacturaPaginado,
    summary="Listar facturas",
    description="""
Devuelve las facturas en páginas, de la más reciente a la más antigua, con búsqueda y filtro por estado.

**Permiso requerido:** `facturas_view`. El rol `admin` siempre tiene acceso. Requiere `Authorization: Bearer <token>`.

**Alcance (se deduce del token):** `admin` ve todas; `cliente`, las que creó + las que tienen su `cliente_id`
(de estas, nunca las `emitida`); cualquier otro usuario (bodeguero), solo las que creó. Si no es suya: **404**.

**Parámetros (todos opcionales):**
- `q`: busca en el **número** de la factura o en el **nombre del cliente** (contiene, sin distinguir mayúsculas).
- `estado`: un solo valor: `emitida`, `entregada`, `firmada`, `rechazada` o `recibida`.
- `page`: número de página, empieza en 1.
- `limit`: elementos por página, por defecto 10 y máximo 100.

**Devuelve:** `{"data": [...], "total": n, "page": p, "limit": l}`. Cada fila trae `id`, `numero`, `estado`,
`fecha_emision`, `cliente_id`, `cliente_nombre`, `bodega_nombre`, `creado_por_id`, `creado_por_nombre` y `total`.
""",
    response_description="Página de facturas con el total que cumple los filtros",
    responses={
        401: ERROR_401,
        422: DOC_422_LISTAR_FACTURAS,
    },
)
def listar_facturas(
    q: str | None = Query(None, description="Texto a buscar en el número o en el nombre del cliente."),
    estado: str | None = Query(None, description="Filtra por estado: emitida, entregada, firmada, rechazada o recibida."),
    page: int = Query(1, ge=1, description="Número de página. Empieza en 1."),
    limit: int = Query(10, ge=1, le=100, description="Elementos por página. Por defecto 10, máximo 100."),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(puede_ver),
):
    """Lista las facturas. El cliente solo ve las suyas (y no los borradores)."""
    return services.listar_facturas(q, estado, page, limit, db, usuario)


# Va ANTES de "/{factura_id}": si no, FastAPI intentaría leer "clientes" como un id y respondería 422
@router.get(
    "/clientes",
    response_model=ClientePaginado,
    summary="Clientes para facturar",
    description="""
Lista los clientes **activos** para elegir el adquiriente al crear una factura.
Solo trae `id`, `nombre`, `tipo_documento` y `numero_documento`, sin acceso al módulo de Usuarios.

**Permiso requerido:** `facturas_create`. El rol `admin` siempre tiene acceso. Requiere `Authorization: Bearer <token>`.

**Parámetros (todos opcionales):**
- `q`: busca en el **nombre** o en el **número de documento** (contiene, sin distinguir mayúsculas).
- `page`: número de página, empieza en 1.
- `limit`: elementos por página, por defecto 10 y máximo 100.

**Devuelve:** `{"data": [...], "total": n, "page": p, "limit": l}`, ordenado por nombre.
El `id` de cada cliente es el que se envía como `cliente_id` en `POST /facturas`.
""",
    response_description="Página de clientes activos",
    responses={
        401: ERROR_401,
        403: DOC_403_GESTION,
        422: DOC_422_LISTAR_CLIENTES_PARA_FACTURAR,
    },
)
def listar_clientes_para_facturar(
    q: str | None = Query(None, description="Texto a buscar en el nombre o en el número de documento."),
    page: int = Query(1, ge=1, description="Número de página. Empieza en 1."),
    limit: int = Query(10, ge=1, le=100, description="Elementos por página. Por defecto 10, máximo 100."),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(puede_crear),
):
    """Clientes activos (datos mínimos) para el selector de cliente de la factura."""
    return services.listar_clientes_para_facturar(q, page, limit, db, usuario)


@router.get(
    "/{factura_id}",
    response_model=FacturaOut,
    summary="Obtener una factura",
    description="""
Devuelve la factura completa: emisor, adquiriente, bodega, detalle, totales, pie de página,
validación electrónica (simulada), datos del software y trazabilidad (incluida la firma).

**Permiso requerido:** `facturas_view`. El rol `admin` siempre tiene acceso. Requiere `Authorization: Bearer <token>`.

**Alcance (se deduce del token):** `admin` ve todas; `cliente`, las que creó + las que tienen su `cliente_id`
(de estas, nunca las `emitida`); cualquier otro usuario (bodeguero), solo las que creó. Si no es suya: **404**.

**Devuelve:** la factura, o 404.
""",
    response_description="La factura completa",
    responses={401: ERROR_401, 404: DOC_404, 422: DOC_422_ID},
)
def obtener_factura(
    factura_id: int = Path(description="Id de la factura.", examples=[1]),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(puede_ver),
):
    """Devuelve una factura por su id (con las reglas de visibilidad del cliente)."""
    return services.obtener_factura(factura_id, db, usuario)


@router.get(
    "/{factura_id}/pdf",
    summary="Descargar la factura en PDF",
    description="""
Genera el PDF de la factura (con la firma del cliente si ya firmó).

**Permiso requerido:** `facturas_pdf`. El rol `admin` siempre tiene acceso. Requiere `Authorization: Bearer <token>`.

**Alcance (se deduce del token):** `admin` ve todas; `cliente`, las que creó + las que tienen su `cliente_id`
(de estas, nunca las `emitida`); cualquier otro usuario (bodeguero), solo las que creó. Si no es suya: **404**.

**Devuelve:** `Content-Type: application/pdf` y `Content-Disposition: attachment; filename="FE-0001.pdf"`.
Como necesita el header `Authorization`, el frontend debe descargarlo como **blob**.
""",
    response_class=Response,
    responses={
        200: {"content": {"application/pdf": {}}, "description": "Archivo PDF de la factura"},
        401: ERROR_401, 404: DOC_404, 422: DOC_422_ID,
    },
)
def descargar_pdf(
    factura_id: int = Path(description="Id de la factura.", examples=[1]),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(puede_pdf),
):
    """Devuelve el PDF de la factura como archivo adjunto."""
    numero, contenido = services.descargar_pdf(factura_id, db, usuario)
    return Response(
        content=contenido,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{numero}.pdf"'},
    )


# ===== CREAR (POST) =====

@router.post(
    "",
    response_model=FacturaOut,
    status_code=status.HTTP_201_CREATED,
    summary="Crear una factura",
    description="""
Crea una factura en estado **`emitida`** (borrador). El cliente todavía no la ve.

**Permiso requerido:** `facturas_create`. El rol `admin` siempre tiene acceso. Requiere `Authorization: Bearer <token>`.

**Cuerpo:**
- `cliente_id` (**obligatorio**): usuario con rol `cliente` y activo.
- `bodega_id` (**obligatorio**): bodega activa. Si factura un bodeguero, debe ser **una de sus bodegas**.
- `forma_pago` (**obligatorio**): `contado` o `credito` (se acepta `crédito`).
- `medio_pago` (**obligatorio**): `efectivo`, `transferencia` o `tarjeta`.
- `fecha_vencimiento`: **obligatoria solo con `credito`**. Con `contado` puede ir `null` u omitirse.
- `observaciones`: **el único opcional**.
- `detalle` (**obligatorio**, al menos 1 línea). En **cada línea, todo es obligatorio**: `tipo_id`, `descripcion`,
  `unidad_medida`, `cantidad` (> 0), `precio_unitario` (≥ 0, sin IVA), `descuento_porcentaje` (0 a 100; envía 0 si no hay)
  e `iva_porcentaje` (0, 5 o 19).

**Errores 422:** además de `detail` (un solo texto), traen `errores` con un mensaje por campo y la ruta completa,
por ejemplo `{"cliente_id": "es obligatorio", "detalle[0].descripcion": "es obligatorio"}`.

**Lo calcula el servidor (no se envía):** número (`FE-0001`, `FE-0002`...), subtotales, descuentos, IVA y totales
de cada línea y de la factura, CUFE simulado, y la copia de los datos del emisor y del cliente.

**Devuelve:** 201 con la factura completa.
""",
    response_description="La factura creada, con número, totales y CUFE",
    responses={
        400: DOC_400_CREAR,
        401: ERROR_401,
        403: DOC_403_GESTION,
        422: DOC_422_CREAR,
    },
)
def crear_factura(
    datos: FacturaCreate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(puede_crear),
):
    """Crea la factura en estado emitida, con su número, sus líneas, sus totales y su CUFE."""
    return services.crear_factura(datos, db, usuario)


# ===== EDITAR (PUT) =====

@router.put(
    "/{factura_id}",
    response_model=FacturaOut,
    summary="Editar una factura (solo emitida)",
    description="""
Edita una factura que todavía está en **`emitida`**. **Solo cambia los campos que se envían.**

**Permiso requerido:** `facturas_edit`. El rol `admin` siempre tiene acceso. Requiere `Authorization: Bearer <token>`.

**Alcance (se deduce del token):** `admin` ve todas; `cliente`, las que creó + las que tienen su `cliente_id`
(de estas, nunca las `emitida`); cualquier otro usuario (bodeguero), solo las que creó. Si no es suya: **404**.

**Reglas:**
- En cualquier otro estado responde 400.
- Si se envía `detalle`, **reemplaza todas** las líneas.
- Si cambia el cliente, se vuelven a copiar sus datos.
- Se recalculan los totales y el CUFE.
- Para borrar `observaciones` se envía `""`. `medio_pago` es obligatorio en la factura: se puede cambiar, no borrar.
- Con `forma_pago: credito` debe haber `fecha_vencimiento` (enviada ahora o ya guardada).

**Devuelve:** la factura actualizada.
""",
    response_description="La factura con los cambios aplicados",
    responses={
        400: DOC_400_ACTUALIZAR,
        401: ERROR_401,
        403: DOC_403_GESTION,
        404: DOC_404,
        422: DOC_422_ACTUALIZAR,
    },
)
def actualizar_factura(
    datos: FacturaUpdate,
    factura_id: int = Path(description="Id de la factura a editar.", examples=[1]),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(puede_editar),
):
    """Edita una factura en estado emitida y recalcula totales y CUFE."""
    return services.actualizar_factura(datos, factura_id, db, usuario)


# ===== ACCIONES (cambian el estado) =====

@router.post(
    "/{factura_id}/entregar",
    response_model=FacturaOut,
    summary="Entregar la factura al cliente",
    description="""
Pasa la factura de **`emitida`** a **`entregada`** y guarda `fecha_entrega`. Desde aquí el cliente la ve y ya no se puede editar ni eliminar.

**Permiso requerido:** `facturas_entregar`. El rol `admin` siempre tiene acceso. Requiere `Authorization: Bearer <token>`.

**Alcance (se deduce del token):** `admin` ve todas; `cliente`, las que creó + las que tienen su `cliente_id`
(de estas, nunca las `emitida`); cualquier otro usuario (bodeguero), solo las que creó. Si no es suya: **404**.
""",
    response_description="La factura en estado entregada",
    responses={400: DOC_400_ESTADO, 401: ERROR_401, 403: DOC_403_GESTION, 404: DOC_404, 422: DOC_422_ID},
)
def entregar_factura(
    factura_id: int = Path(description="Id de la factura.", examples=[1]),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(puede_entregar),
):
    return services.entregar_factura(factura_id, db, usuario)


@router.post(
    "/{factura_id}/aceptar",
    response_model=FacturaOut,
    summary="Aceptar y firmar la factura (cliente)",
    description="""
El cliente acepta la factura y la firma: pasa de **`entregada`** a **`firmada`** y guarda la firma y `fecha_respuesta`.

**Permiso requerido:** `facturas_aceptar`. El rol `admin` siempre tiene acceso. Requiere `Authorization: Bearer <token>`.

Además, solo el **cliente de la factura** puede hacerlo: cualquier otro usuario recibe 403.

**Cuerpo:** `{"firma": "data:image/png;base64,..."}`: imagen PNG en base64, máximo 500 KB.
""",
    response_description="La factura firmada",
    responses={
        400: DOC_400_ESTADO, 401: ERROR_401, 403: DOC_403_CLIENTE, 404: DOC_404,
        422: DOC_422_ACEPTAR,
    },
)
def aceptar_factura(
    datos: FirmaIn,
    factura_id: int = Path(description="Id de la factura.", examples=[1]),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(puede_aceptar),
):
    return services.aceptar_factura(datos, factura_id, db, usuario)


@router.post(
    "/{factura_id}/rechazar",
    response_model=FacturaOut,
    summary="Rechazar la factura (cliente)",
    description="""
El cliente rechaza la factura: pasa de **`entregada`** a **`rechazada`** (estado final) y guarda el motivo y `fecha_respuesta`.
Para corregirla, el bodeguero crea una factura nueva.

**Permiso requerido:** `facturas_rechazar`. El rol `admin` siempre tiene acceso. Requiere `Authorization: Bearer <token>`.

Además, solo el **cliente de la factura** puede hacerlo: cualquier otro usuario recibe 403.

**Cuerpo:** `{"motivo": "texto"}`, de 1 a 255 caracteres.
""",
    response_description="La factura rechazada",
    responses={
        400: DOC_400_ESTADO, 401: ERROR_401, 403: DOC_403_CLIENTE, 404: DOC_404,
        422: DOC_422_RECHAZAR,
    },
)
def rechazar_factura(
    datos: RechazoIn,
    factura_id: int = Path(description="Id de la factura.", examples=[1]),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(puede_rechazar),
):
    return services.rechazar_factura(datos, factura_id, db, usuario)


@router.post(
    "/{factura_id}/recibir",
    response_model=FacturaOut,
    summary="Recibir la factura firmada",
    description="""
El bodeguero recibe la factura firmada: pasa de **`firmada`** a **`recibida`** (estado final) y guarda `fecha_recepcion`.

**Permiso requerido:** `facturas_recibir`. El rol `admin` siempre tiene acceso. Requiere `Authorization: Bearer <token>`.

**Alcance (se deduce del token):** `admin` ve todas; `cliente`, las que creó + las que tienen su `cliente_id`
(de estas, nunca las `emitida`); cualquier otro usuario (bodeguero), solo las que creó. Si no es suya: **404**.
""",
    response_description="La factura recibida",
    responses={400: DOC_400_ESTADO, 401: ERROR_401, 403: DOC_403_GESTION, 404: DOC_404, 422: DOC_422_ID},
)
def recibir_factura(
    factura_id: int = Path(description="Id de la factura.", examples=[1]),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(puede_recibir),
):
    return services.recibir_factura(factura_id, db, usuario)


# ===== ELIMINAR (DELETE) =====

@router.delete(
    "/{factura_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar una factura (solo emitida)",
    description="""
Elimina una factura que todavía está en **`emitida`**, junto con sus líneas. En cualquier otro estado responde 400.

**Permiso requerido:** `facturas_delete`. El rol `admin` siempre tiene acceso. Requiere `Authorization: Bearer <token>`.

**Alcance (se deduce del token):** `admin` ve todas; `cliente`, las que creó + las que tienen su `cliente_id`
(de estas, nunca las `emitida`); cualquier otro usuario (bodeguero), solo las que creó. Si no es suya: **404**.

**Devuelve:** 204 **sin cuerpo**.
""",
    response_description="Factura eliminada. La respuesta no tiene cuerpo",
    responses={400: DOC_400_ESTADO, 401: ERROR_401, 403: DOC_403_GESTION, 404: DOC_404, 422: DOC_422_ID},
)
def eliminar_factura(
    factura_id: int = Path(description="Id de la factura a eliminar.", examples=[1]),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(puede_eliminar),
):
    services.eliminar_factura(factura_id, db, usuario)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
