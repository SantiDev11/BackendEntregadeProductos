from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError

from app.database import Base, engine
import app.modulos  # registra todos los modelos para que create_all los vea
from app.modulos.auth import router as auth
from app.modulos.tipos import router as tipos
from app.modulos.bodegas import router as bodegas
from app.modulos.permisos import router as permisos
from app.modulos.roles import router as roles
from app.modulos.usuarios import router as usuarios
from app.modulos.facturas import router as facturas
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
    {"name": "Tipos", "description": "CRUD de tipos de producto. Permisos `tipos_view/create/edit/delete`."},
    {"name": "Bodegas", "description": "CRUD de bodegas (puntos de despacho). Permisos `bodegas_*`. El admin ve todas; los demás solo las suyas."},
    {"name": "Permisos", "description": "Catálogo de permisos. Permisos `permisos_*`."},
    {"name": "Roles", "description": "CRUD de roles y su plantilla de permisos. Permisos `roles_*`."},
    {"name": "Usuarios", "description": "CRUD de usuarios y sus permisos (la contraseña nunca se devuelve). Permisos `usuarios_*`."},
    {"name": "Facturas", "description": "Órdenes de entrega (la orden es la factura): borrador, entrega, firma o rechazo del cliente, recepción y PDF."},
    {"name": "Inicio", "description": "Comprobar que la API está funcionando."},
]

# docs_url=None: el /docs por defecto se reemplaza por uno con los endpoints ordenados
app = FastAPI(title="Entrega de Productos", lifespan=lifespan, docs_url=None, openapi_tags=TAGS)
configurar_docs(app)

# CORS: permite que el frontend (Vue) llame a la API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(tipos.router)
app.include_router(bodegas.router)
app.include_router(permisos.router)
app.include_router(roles.router)
app.include_router(usuarios.router)
app.include_router(facturas.router)

# Errores de validación (422) como {"detail": "texto"}
app.add_exception_handler(RequestValidationError, validation_exception_handler)


@app.get("/", tags=["Inicio"])
def inicio():
    return {"mensaje": "API Entrega de Productos funcionando"}
