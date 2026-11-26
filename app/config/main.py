from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError

from app.config.database import Base, engine
import app.modulos  # registra todos los modelos para que create_all los vea
from app.modulos.auth import router as auth
from app.modulos.registro import router as registro
from app.modulos.empresas import router as empresas
from app.modulos.tipos import router as tipos
from app.modulos.bodegas import router as bodegas
from app.modulos.permisos import router as permisos
from app.modulos.roles import router as roles
from app.modulos.usuarios import router as usuarios
from app.modulos.clientes import router as clientes
from app.modulos.facturas import router as facturas
from app.modulos.estadisticas import router as estadisticas
from app.core.errors import validation_exception_handler
from app.core.docs import configurar_docs


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Al arrancar: crea las tablas que no existan
    Base.metadata.create_all(bind=engine)
    yield


# Grupos de /docs, en este orden y con su descripción
TAGS = [
    {"name": "Auth", "description": "Inicio de sesión (token JWT) y datos del usuario de la sesión, con sus permisos. "
                                    "**Acceso por permisos:** cada endpoint exige un permiso (`modulo_accion`) que se lee "
                                    "de la BD en cada petición; el rol `admin` siempre tiene acceso."},
    {"name": "Empresas", "description": "CRUD de empresas, y aprobarlas, rechazarlas o suspenderlas. Solo el rol `admin`."},
    {"name": "Tipos", "description": "CRUD de tipos de producto. Permisos `tipos_view/create/edit/delete`."},
    {"name": "Bodegas", "description": "CRUD de bodegas (puntos de despacho). Permisos `bodegas_*`. El admin ve todas; los demás solo las suyas."},
    {"name": "Permisos", "description": "Catálogo de permisos. Permisos `permisos_*`."},
    {"name": "Roles", "description": "CRUD de roles y su plantilla de permisos. Permisos `roles_*`."},
    {"name": "Usuarios", "description": "CRUD de usuarios y sus permisos (la contraseña nunca se devuelve). Permisos `usuarios_*`."},
    {"name": "Clientes", "description": "Buscar el cliente al que se le va a facturar. Permiso `facturas_create`."},
    {"name": "Facturas", "description": "Órdenes de entrega (la orden es la factura): borrador, entrega, firma o rechazo del cliente, recepción y PDF."},
    {"name": "Estadísticas", "description": "Panel de estadísticas según el rol (tarjetas y gráficos). Permiso `estadisticas_view`."},
    {"name": "Inicio", "description": "Comprobar que la API está funcionando."},
]

# Descripción del proyecto que aparece debajo del título en /docs
DESCRIPCION = """
API para gestionar la **entrega de productos desde bodegas a clientes**, con **factura electrónica simulada**.

**Qué hace:**
- Cada bodega tiene su propio catálogo de **tipos de producto**.
- El bodeguero crea una **factura** (orden de entrega) para un cliente, con sus líneas de productos. El servidor calcula
  descuentos, IVA y totales, y le asigna número (`FE-0001`), CUFE simulado y QR.
- La factura sigue este flujo: **emitida** → **entregada** al cliente → el cliente la **firma** (acepta) o la
  **rechaza** con un motivo → el bodeguero la marca como **recibida**. En cualquier momento se puede descargar en **PDF**.

**Roles:**
- **Admin:** gestiona todo (usuarios, roles, permisos, bodegas, tipos y facturas).
- **Bodeguero:** maneja sus bodegas y sus tipos, y emite y entrega facturas. Solo ve las facturas que creó.
- **Cliente:** ve sus facturas, las acepta con su firma o las rechaza.

**Seguridad:**
- Para probar aquí: pulsa **Authorize**, escribe tu **correo** en *username* y tu **contraseña** en *password*
  y pulsa **Authorize**. La sesión queda guardada aunque recargues la página (dura 60 minutos).
- Cada endpoint exige un permiso que se revisa por usuario.
- El token de acceso se puede renovar con `POST /refresh` usando el `refresh_token` que devuelve el login.
"""

# docs_url=None: el /docs por defecto se reemplaza por uno con los endpoints ordenados
app = FastAPI(title="Entrega de Productos", description=DESCRIPCION, version="1.0.0",
              lifespan=lifespan, docs_url=None, openapi_tags=TAGS)
configurar_docs(app)

# CORS: permite que el frontend (Vue) y la app móvil (Capacitor) llamen a la API
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",       # Vite dev server (front web)
        "http://localhost",            # Android WebView (build producción)
        "capacitor://localhost",       # iOS WebView (build producción)
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth.router)
app.include_router(registro.router)
app.include_router(empresas.router)
app.include_router(tipos.router)
app.include_router(bodegas.router)
app.include_router(permisos.router)
app.include_router(roles.router)
app.include_router(usuarios.router)
app.include_router(clientes.router)
app.include_router(facturas.router)
app.include_router(estadisticas.router)

# Errores de validación (422) como {"detail": "texto"}
app.add_exception_handler(RequestValidationError, validation_exception_handler)


@app.get("/", tags=["Inicio"])
def inicio():
    return {"mensaje": "API Entrega de Productos funcionando"}
