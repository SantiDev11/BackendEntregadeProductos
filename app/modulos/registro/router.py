# Registro público (no pide sesión): clientes y empresas.
# Aquí solo está la ruta y su documentación. La lógica está en services.py, las validaciones en helpers.py
# y los errores (mensajes y ejemplos /docs) en errors.py.
from typing import Union

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.modulos.registro import services
from app.modulos.registro.errors import DOC_400, DOC_422
from app.modulos.registro.helpers import RutaRegistro
from app.modulos.registro.schemas import Registro, RegistroClienteOut, RegistroEmpresaOut

router = APIRouter(tags=["Auth"], route_class=RutaRegistro)


@router.post(
    "/register",
    response_model=Union[RegistroClienteOut, RegistroEmpresaOut],
    status_code=status.HTTP_201_CREATED,
    summary="Registro público",
    description="""
Crea una cuenta nueva. `tipo` decide qué se registra y qué campos lleva.

**Quién puede usarlo:** cualquiera. Es público y no requiere token. No devuelve token: después se usa `POST /login`.

**`"tipo": "cliente"`** — todos obligatorios: `nombre`, `tipo_documento`, `numero_documento`, `telefono`, `correo`, `contrasena`.
El cliente queda **activo** y puede iniciar sesión de inmediato.

**`"tipo": "empresa"`** — todos obligatorios: `razon_social`, `nit`, `telefono`, `direccion`, `representante`, `correo`, `contrasena`.
Crea la empresa en estado **pendiente** y su usuario (rol `empresa`, con ese correo y contraseña, y nombre = `representante`).
No puede iniciar sesión (403) hasta que un admin la apruebe.

**Reglas:**
- El correo es único en todo el sistema; el documento es único entre usuarios y el NIT entre empresas (sin contar el dígito).
- `telefono`: solo números, de 7 a 15. `nit`: `900123456-1`. `contrasena`: de 8 a 72 caracteres.
- El rol, el estado y los permisos los pone el servidor: si se envían, se ignoran.
- Todo se guarda junto: si algo falla, no queda nada a medias.
""",
    response_description="La cuenta creada, o la empresa pendiente de aprobación",
    responses={400: DOC_400, 422: DOC_422},
)
def registrar(datos: Registro, db: Session = Depends(get_db)):
    """Registra un cliente o una empresa."""
    return services.registrar(datos, db)
