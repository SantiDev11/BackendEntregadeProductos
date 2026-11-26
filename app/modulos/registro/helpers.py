# Validaciones y ayudas del registro público. Si algo no se cumple, lanzan el error que corresponde.
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from sqlalchemy.orm import Session

from app.modulos.empresas.helpers import validate_unique_nit
from app.modulos.empresas.schemas import EmpresaCreate
from app.modulos.registro.errors import MSG_TIPO
from app.modulos.registro.schemas import RegistroCliente
from app.modulos.roles.models import Rol
from app.modulos.usuarios.helpers import validate_unique_usuario_documento, validate_unique_usuario_email


def validate_repetidos(db: Session, datos: RegistroCliente | EmpresaCreate) -> None:
    """Lanza 400 si el correo, el documento (cliente) o el NIT (empresa) ya están registrados."""
    validate_unique_usuario_email(db, datos.correo)
    if isinstance(datos, RegistroCliente):
        validate_unique_usuario_documento(db, datos.numero_documento)
    else:
        validate_unique_nit(db, datos.nit.split("-")[0])


def rol_por_nombre(db: Session, nombre: str) -> Rol:
    """El rol del nuevo usuario. Si no existe es un error de instalación (falta el seed o la migración 007)."""
    return db.query(Rol).filter(Rol.nombre == nombre).one()


def _limpiar(error: dict) -> dict:
    """Pydantic agrega el `tipo` a la ruta del error (body, cliente, nombre): se quita para que el campo
    sea "nombre", igual que en el resto de la API. También traduce los errores del propio `tipo`."""
    if error["type"] == "union_tag_not_found":
        return {**error, "type": "missing", "loc": ("body", "tipo")}
    if error["type"] == "union_tag_invalid":
        return {**error, "type": "regla_negocio", "loc": ("body", "tipo"), "msg": MSG_TIPO}
    loc = tuple(error["loc"])
    return {**error, "loc": loc[:1] + loc[2:] if loc[1:2] in (("cliente",), ("empresa",)) else loc}


class RutaRegistro(APIRoute):
    """Ruta que limpia los errores 422 del registro antes de que los responda el manejador general."""

    def get_route_handler(self):
        manejador = super().get_route_handler()

        async def limpiar_errores(request):
            try:
                return await manejador(request)
            except RequestValidationError as error:
                raise RequestValidationError([_limpiar(e) for e in error.errors()])

        return limpiar_errores
